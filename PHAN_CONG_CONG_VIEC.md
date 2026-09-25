# Thống nhất chung và phân công công việc nhóm 4 người — L3B Multi-Agent MCP + A2A

> Tài liệu triển khai cho nhóm 4 người. Điền tên thật vào bảng phân công trước khi bắt đầu. **Mỗi người sở hữu một module agent riêng**, phát triển và kiểm thử độc lập, sau đó mới ghép vào `solve_case()`. Bốn module và `solve_case()` đã có bản triển khai; đây là phân công để mỗi người kiểm thử, review và tiếp tục cải tiến phần mình sở hữu.

## 1. Thống nhất chung — đọc trước khi chia việc

### 1.1. Mục tiêu và phạm vi

- Xây dựng luồng điều tra khiếu nại thương mại điện tử cho **L3B**, xử lý đủ 100 case trong `case-set.json` và `inputs/`.
- Với mỗi case, xác định đúng đơn hàng và các thực thể liên quan; kiểm tra lịch sử khách hàng, sản phẩm, vận chuyển, thanh toán, hoàn tiền và chính sách; giải quyết mâu thuẫn nguồn; đưa ra kết luận và hành động dựa trên bằng chứng.
- Hệ thống phải thể hiện sự phối hợp giữa các agent bằng trace có thể quan sát, đồng thời tiết kiệm số lần gọi MCP. Không cần một framework multi-agent cụ thể; cần luồng bàn giao và kết quả đúng.
- Đầu ra cuối cùng là `outputs/<case_id>.json` cho từng case, `traces/trace.jsonl` và gói `dist/submission-v3.zip`. Không sửa ý nghĩa của các schema trong `contracts/`.

### 1.2. Chốt kiến trúc trước khi chia code

**Có. Đây là bước đầu tiên bắt buộc của nhóm.** Nếu chưa thống nhất kiến trúc và hợp đồng giữa các module, bốn người có thể viết bốn phần chạy riêng nhưng không ghép được. Cả nhóm chốt và ghi phiên bản đầu vào `ARCHITECTURE.md` **trước khi** triển khai logic nghiệp vụ; khi code thay đổi thiết kế, cập nhật tài liệu cùng lúc.

Kiến trúc đề xuất cho repo hiện tại:

```text
CLI -> workflow.py (Coordinator/điểm ghép)
          |
          +-> agents/entity_customer.py  -> kết quả xác định order/customer
          +-> agents/order_fulfillment.py -> kết quả order/product/shipment
          +-> agents/payment_refund.py    -> kết quả payment/refund
          +-> agents/policy_verifier.py   -> policy/conflict/decision + xác minh draft
          |
          +-> output L3B + trace

Các module dùng chung EvidenceGateway, TraceWriter và agent_contracts.py.
```

`agents/` và `agent_contracts.py` đã được triển khai. Bốn module tương ứng bốn người; `workflow.py` chỉ điều phối, ghép kết quả và không chứa lại logic chuyên môn của từng module. MCP tool là công cụ **gateway cung cấp**, không phải bốn tool mà nhóm phải tự viết. Mỗi người chịu trách nhiệm một module gọi **nhóm MCP tool thuộc miền dữ liệu của mình** sau khi tool discovery.

Trước khi bắt đầu code, cả nhóm thống nhất và ghi rõ sáu quyết định sau:

1. **Ranh giới module:** mỗi người sửa module mình sở hữu và test tương ứng; không gọi trực tiếp module của người khác. `workflow.py` là nơi duy nhất sắp thứ tự gọi và bàn giao.
2. **Hợp đồng giao tiếp:** thống nhất một `AgentTask` và `AgentResult` trong `agent_contracts.py`. Task tối thiểu có `case_id`, actor gửi/nhận, scope/ID đã xác minh, câu hỏi cần trả lời và giới hạn truy vấn. Result tối thiểu có `case_id`, actor, status, findings theo miền, `evidence_refs`, confidence, unresolved issues và lỗi có cấu trúc. Tên trường/kiểu dữ liệu cụ thể phải được chốt trong file trước khi bốn người bắt đầu module.
3. **Thứ tự phụ thuộc:** entity/customer chạy trước để xác định order; order/fulfillment và payment/refund có thể chạy độc lập trên cùng scope đã xác minh; policy/decision nhận cả ba kết quả; verifier kiểm tra draft cuối cùng trước khi trả output. Nếu entity ambiguous/not_found, các bước sau chỉ được dùng scope được chứng minh.
4. **MCP và evidence:** phân quyền domain tool cho từng module, quy tắc discovery, cache theo case, giới hạn retry/query, cách lưu và bàn giao `evidence_ref`; không đưa raw response chưa validate qua ranh giới module.
5. **Kết luận và lỗi:** enum status chung, ngưỡng confidence, cách trả thiếu bằng chứng/xung đột/timeout, mã quyết định, thứ tự ưu tiên nguồn và số vòng sửa tối đa sau verifier. Không để mỗi module tự định nghĩa khác nhau.
6. **Trace và output:** actor name cố định, ai emit `task_assigned`, `handoff`, `tool_result_consumed`, `policy_decided`, `verification_completed`; mapping từng findings vào schema L3B; ai chịu trách nhiệm các trường dùng chung như `assessment`, `evidence_refs`, `resolution_actions`.

**Điều kiện kết thúc bước kiến trúc:** `ARCHITECTURE.md` có sơ đồ, bảng ownership/tool permission, hợp đồng A2A, quy tắc evidence/conflict, failure/efficiency và checklist verifier; cả bốn người review. Sau đó mới triển khai riêng từng module.

### 1.3. Nguồn chuẩn và quy tắc quyết định

1. **Schema và scoring policy công khai** trong `contracts/` là nguồn chuẩn cho cấu trúc output, trace, evidence và trọng số chấm điểm. Đọc `contracts/schemas/l3b-output-v2.schema.json`, `trace-event-v1.schema.json`, `mcp-evidence-response-v1.schema.json` và `contracts/scoring/scoring-policy-v2.json` trước khi lập trình.
2. **Dữ liệu case** nêu yêu cầu cần điều tra, không tự nó chứng minh khiếu nại là đúng. `claimed_order_id`, `candidate_order_ids`, `customer_unique_id_hint` chỉ là đầu mối; phải xác minh bằng MCP evidence.
3. **MCP response** là bằng chứng được cấp cho đúng team/run/case. Giữ nguyên `evidence_ref`, không tự tạo, không sửa, không dùng chéo case. Chỉ đưa ref liên quan đến kết luận vào output và trace.
4. **Chính sách** là căn cứ quyết định trách nhiệm, hoàn tiền và hành động. Khi nguồn mâu thuẫn, ghi rõ trường bị mâu thuẫn, các nguồn, nguồn được chọn hoặc chưa thể chọn, cùng mã lý do trong `data_conflicts`.
5. Không có đủ bằng chứng thì thể hiện `ambiguous`, `not_found`, `insufficient_evidence` hoặc `needs_investigation` khi phù hợp; không điền dữ liệu suy đoán để output trông đầy đủ.

### 1.4. Luồng xử lý thống nhất

```text
Input case
  -> Coordinator tiếp nhận, lập kế hoạch điều tra
  -> Entity/customer xác minh order và customer
  -> Order/product/Shipment và Payment/refund điều tra trên cùng phạm vi đã xác minh
  -> Policy/Conflict resolver đối chiếu nguồn, trách nhiệm, mức hoàn tiền
  -> Coordinator tạo draft output; Verifier kiểm tra draft
  -> Coordinator tổng hợp output, ghi trace, hoàn tất case
```

- `solve_case(case, gateway, trace)` trong `src/student_agent/workflow.py` là điểm tích hợp duy nhất mà CLI gọi. Giữ nguyên chữ ký này; bốn module agent trả kết quả qua hợp đồng chung và chỉ `workflow.py` ghép output.
- Task/result A2A là **quy ước thiết kế nội bộ cần triển khai**; không nhầm với schema trace công khai. Bàn giao bằng dữ liệu có cấu trúc, không truyền lời giải thích tự do làm đầu vào quyết định cho agent sau.
- `Coordinator` điều phối và tổng hợp; agent chuyên môn chỉ kết luận trong phạm vi được giao. `Verifier` phải kiểm tra kết quả tổng hợp trước khi finalize, không chỉ kiểm tra JSON có đúng schema.
- Mọi truy vấn MCP phải dùng tool đã được khám phá bằng `day09 mcp-tools`/`gateway.list_tools()`; tên tool trong ví dụ README không thay cho danh sách tool thực tế. Quyền gọi tool được giới hạn theo nhu cầu của từng vai trò.

### 1.5. Bằng chứng, trace và chi phí MCP

- Gọi MCP luôn kèm đúng `case_id`; validate response trước khi dùng. Cache theo **từng case** và theo tham số truy vấn để tránh gọi lại cùng một bằng chứng. Không quét rộng hoặc gọi mọi tool theo mặc định.
- Mỗi kết luận quan trọng phải truy ngược được đến một hoặc nhiều `evidence_ref`. Với từng `claim_id`, nếu tạo `claim_assessments`, phải ghi verdict, confidence và refs riêng của claim đó.
- Khi agent **dùng** bằng chứng, phát `tool_result_consumed` với actor, tên tool và refs. Trace phải có luồng `case_received` → `task_assigned`/`handoff` → `verification_completed` → `case_finalized` theo đúng thứ tự. `case_received` và `case_finalized` đã được CLI ghi; không phát trùng khi tích hợp.
- Trace chỉ chứa sự kiện có thể quan sát, quyết định dạng mã và metadata cần thiết; không ghi prompt, chain-of-thought, API key hoặc dữ liệu nhạy cảm không cần thiết.
- Retry có giới hạn, chỉ cho lỗi tạm thời; timeout hoặc thiếu dữ liệu phải chuyển sang kết quả có trạng thái rõ ràng. Tất cả MCP calls được audit và tính vào hiệu quả, kể cả cuộc gọi không dùng trong output.

### 1.6. Quy ước làm việc và tiêu chí hoàn thành chung

- **Nhịp làm việc:** cả bốn người cùng chốt kiến trúc và hợp đồng task/result một lần ở đầu; sau đó phát triển bốn module **song song** bằng dữ liệu giả lập. Người 2/3 dùng EntityResult mẫu; Người 4 dùng ba AgentResult mẫu. Không ai phải chờ code của người khác mới bắt đầu phần riêng.
- **Nghiệm thu chéo:** mỗi người review module được phân công khi có bản bàn giao, có thể review trong lúc các module khác vẫn đang phát triển. Review tập trung vào đúng hợp đồng, evidence/trace, test và khả năng ghép. Chỉ những lỗi interface hoặc nghiệp vụ ảnh hưởng tích hợp mới cần sửa trước khi merge vào `workflow.py`; không tổ chức bốn vòng nghiệm thu tuần tự.
- Mỗi module có **một người chịu trách nhiệm chính** và **một người review**. Chốt `agent_contracts.py` trước; không cùng sửa `workflow.py` trong giai đoạn phát triển riêng. Mỗi người có thể chạy test module với gateway giả lập và task/result mẫu theo hợp đồng đã chốt.
- Khi thay đổi code, comment bằng **tiếng Anh dễ hiểu**, không dùng icon trong code. Không commit `.env`, Team API Key, input thi đấu, output, trace, ZIP hoặc log. Giữ nguyên tên repo khi fork theo README.
- Thử trên các case có tình huống khác nhau: sai candidate, nhiều claim, giao chậm do seller/logistics, split payment, refund, bằng chứng thiếu hoặc xung đột. Test phải kiểm tra quy tắc nghiệp vụ và bàn giao, không chỉ lặp lại logic implementation.
- Hoàn thành toàn nhóm khi: `day09 validate-inputs` xác nhận đủ 100 input; `day09 run` tạo đủ 100 output; `day09 validate` pass; `day09 package --output dist/submission-v3.zip` tạo ZIP đúng cấu trúc; nhóm kiểm tra thủ công một số case và cập nhật `ARCHITECTURE.md` theo thiết kế thực tế.
- Ưu tiên xử lý các lỗi có thể làm case nhận 0 điểm: sai `case_id`, output không chấm được theo schema, thiếu bằng chứng bắt buộc, `evidence_ref` không tồn tại hoặc không thuộc đúng team/run/case. Sau đó tối ưu semantic, evidence, consistency, calibration, workflow và efficiency.

## 2. Bảng phân công tổng quan

Điền tên thật vào cột thành viên. Mỗi người dùng file riêng làm tài liệu công việc; mỗi file chứa lại phần thống nhất chung để có thể đọc độc lập. Nếu nhóm đổi quyết định chung, cập nhật cả bốn file để tránh lệch nội dung.

| Người | Thành viên | File làm việc riêng | Một module sở hữu | Nhóm MCP tool cần dùng sau discovery | Người review chính |
| --- | --- | --- | --- | --- | --- |
| Người 1 | _Điền tên_ | [NGUOI_1.md](phan-cong/NGUOI_1.md) | `agents/entity_customer.py` | Order và customer để xác định thực thể | Người 4 |
| Người 2 | _Điền tên_ | [NGUOI_2.md](phan-cong/NGUOI_2.md) | `agents/order_fulfillment.py` | Order, item, seller, product, shipment | Người 1 |
| Người 3 | _Điền tên_ | [NGUOI_3.md](phan-cong/NGUOI_3.md) | `agents/payment_refund.py` | Payment và refund | Người 4 |
| Người 4 | _Điền tên_ | [NGUOI_4.md](phan-cong/NGUOI_4.md) | `agents/policy_verifier.py` | Policy; đọc findings của ba module để giải xung đột và verify | Người 2 |

**Phần dùng chung sau khi đã chốt kiến trúc:** `agent_contracts.py` do Người 1 tạo bản đầu và cả nhóm review; `workflow.py` do Người 1 ghép sau khi bốn module có test độc lập; `ARCHITECTURE.md` do Người 4 ghi lại quyết định đã được cả nhóm review. Mỗi người có quyền đề xuất sửa hợp đồng, nhưng thay đổi giao diện phải được thông báo cho cả bốn người trước khi sửa code phụ thuộc.

## 3. Công việc chi tiết của từng người

### Người 1 — Module xác định thực thể và ngữ cảnh khách hàng

**Module sở hữu:** `src/student_agent/agents/entity_customer.py`. **Chức năng:** từ input và MCP evidence, xác định đơn hàng/khách hàng đúng, loại candidate sai và trả kết quả entity/customer có cấu trúc. **Công việc tích hợp sau cùng:** sở hữu `agent_contracts.py` bản đầu và `workflow.py` sau khi bốn module đã bàn giao.

**Cần làm:**

1. Cùng cả nhóm chốt interface trước khi code. Tạo `agent_contracts.py` theo quyết định đã review và cung cấp task/result mẫu để ba người còn lại lập trình, test mà chưa cần `workflow.py`.
2. Đọc các trường input: `case_id`, `opened_at`, `customer_request`, `candidate_order_ids`, `customer_unique_id_hint`, `investigation_scope`, `policy_version`. Lập danh sách câu hỏi cần xác minh theo từng case, không giả định `claimed_order_id` là đúng.
3. Thiết kế và triển khai entity resolution: truy vấn evidence cần thiết để so khớp order, customer và candidate; xếp hạng/chấp nhận/từ chối candidate; xác định khi nào `resolved`, `ambiguous` hoặc `not_found`; ghi rõ `resolved_order_ids`, `rejected_candidates`, confidence và lý do có thể kiểm chứng.
4. Trả `AgentResult` cho Coordinator gồm scope hợp lệ, các candidate bị loại, evidence refs và điểm chưa rõ. Module này không tự gọi module của Người 2 hoặc Người 3.
5. Truy xuất customer history khi `include_customer_history` yêu cầu; phân biệt đơn liên quan với đơn đang khiếu nại; điền `customer_context.customer_unique_id`, `related_order_ids` bằng evidence cùng case.
6. Test module độc lập với gateway giả lập cho candidate đúng, sai, mơ hồ, không tìm thấy và customer hint lệch. Module phải import/chạy được khi ba module kia chưa hoàn thành.
7. **Chỉ ở giai đoạn tích hợp:** viết Coordinator trong `workflow.py` gọi bốn module theo thứ tự kiến trúc, emit `task_assigned`/`handoff`, ghép toàn bộ trường `l3b-output-v2`, quản lý query budget theo case và gọi verifier trước khi trả output.

**Bàn giao độc lập:** module entity/customer, task/result mẫu, test và hướng dẫn cách gọi. **Bàn giao sau khi gộp:** `workflow.py` cùng mapping output/trace. **Xong khi:** candidate sai được loại có căn cứ, case mơ hồ không bị gán nhầm và module chạy độc lập theo interface đã chốt.

### Người 2 — Module đơn hàng, sản phẩm và vận chuyển

**Module sở hữu:** `src/student_agent/agents/order_fulfillment.py`. **Chức năng:** nhận scope order đã xác minh, trả findings về order/product/shipment; không phụ thuộc code Người 1 ngoài hợp đồng task/result chung.

**Cần làm:**

1. Nhận `case_id`, order ID đã được Người 1 xác minh và scope điều tra. Lấy evidence order/item/seller/product theo đúng nhu cầu; không lấy thông tin của candidate đã bị loại để kết luận về đơn chính.
2. Kiểm tra trạng thái đơn, item, seller, sản phẩm, số lượng và các tình huống thiếu hàng, hủy đơn hoặc không khớp sản phẩm. Trả về các ID chính xác cho `affected_entities.order_ids`, `item_ids`, `seller_ids`.
3. Khi `include_product_context` bật, kiểm tra product context liên quan trực tiếp đến claim; nêu nguồn evidence và điều gì vẫn chưa xác minh được.
4. Dựng timeline shipment từ các mốc có evidence: chuẩn bị/bàn giao, vận chuyển, dự kiến giao, thực tế giao, thất lạc hoặc hoàn trả. So sánh mốc thời gian trước khi chọn `shipment_analysis.verdict` (`on_time`, `seller_delay`, `logistics_delay`, `lost`, `returned`, `conflicting`, `insufficient_evidence`).
5. Xác định `late_seller_ids` chỉ khi evidence đủ để quy trách nhiệm seller; đặt `timeline_complete` đúng thực tế; bàn giao `shipment_ids` và các điểm nguồn mâu thuẫn cho Người 4.
6. Đối chiếu từng claim về đơn hàng/sản phẩm/vận chuyển với evidence; gửi verdict đề xuất và refs cho Người 1. Không tự quyết định hoàn tiền nếu chưa có kết luận của Người 3 và chính sách của Người 4.
7. Viết test độc lập với task entity mẫu và gateway giả lập cho giao đúng hạn, seller delay, logistics delay, thiếu timeline, item/seller không khớp. Không chỉnh `workflow.py` trong giai đoạn phát triển riêng.

**Bàn giao:** module, test, findings order/product/shipment, timeline, danh sách ID, claim verdict đề xuất, evidence refs và mâu thuẫn nguồn. **Xong khi:** chạy được độc lập bằng task mẫu; timeline và trách nhiệm tương ứng với evidence; các ID thuộc order được xác minh.

### Người 3 — Module thanh toán, hoàn tiền và đối soát tài chính

**Module sở hữu:** `src/student_agent/agents/payment_refund.py`. **Chức năng:** nhận scope order đã xác minh, tái dựng giao dịch tiền và trả findings tài chính; không phụ thuộc code Người 2.

**Cần làm:**

1. Nhận order ID đã resolve và các item/seller liên quan. Lấy evidence payment, capture, refund theo `case_id`; ghi `payment_references` thuộc đúng đơn.
2. Đối soát tổng capture với nghĩa vụ thanh toán, bao gồm split payment; phân biệt nhiều phương thức thanh toán hợp lệ với `duplicate_capture`. Phân tích capture mismatch, refund pending, refund failed hoặc đã refund dựa trên trạng thái giao dịch thực tế.
3. Tính `captured_total_brl`, `refunded_total_brl`, `refundable_total_brl` từ bằng chứng; xử lý nhiều giao dịch, refund từng phần và trường hợp thiếu số liệu. Không tự biến `null` thành 0; tránh đếm trùng capture/refund.
4. Đề xuất `payment_analysis.verdict` theo enum schema và cung cấp bảng đối soát ngắn gọn cho Người 4: giao dịch, số tiền, trạng thái, refs, khoản có thể hoàn và khoản đã hoàn.
5. Phối hợp Người 4 tính `financial_resolution.recommended_refund_brl` và `refund_lines` theo chính sách, bảo đảm tổng refund lines bằng mức đề xuất và không hoàn vượt phần đủ điều kiện sau khi xét khoản đã refund.
6. Đối chiếu claim về thanh toán/hoàn tiền và gửi verdict cùng evidence refs cho Người 1; đánh dấu xung đột giữa payment và refund source thay vì chọn tùy ý.
7. Viết test độc lập với task entity mẫu và gateway giả lập cho split payment hợp lệ, capture trùng, refund một phần, refund failed và thiếu số tiền. Không chỉnh `workflow.py` trong giai đoạn phát triển riêng.

**Bàn giao:** module, test, findings payment/refund, bảng đối soát, `payment_references`, số tiền BRL, claim verdict đề xuất và refs. **Xong khi:** chạy được độc lập bằng task mẫu; split payment hợp lệ không bị kết luận là thu trùng; các tổng số nhất quán.

### Người 4 — Module chính sách, quyết định và kiểm chứng

**Module sở hữu:** `src/student_agent/agents/policy_verifier.py`. **Chức năng:** nhận ba `AgentResult`, áp dụng policy, giải quyết xung đột, đề xuất quyết định; expose thêm hàm verifier nhận draft output để kiểm chứng trước finalize. Việc chạy package là trách nhiệm phát hành sau khi gộp, không phải chức năng bên trong module.

**Cần làm:**

1. Tra cứu policy đúng `policy_version` của case qua tool đã khám phá. Xác định điều kiện hoàn tiền, trách nhiệm seller/platform/logistics/payment provider và hành động được phép; ghi `policy_decided` với mã quyết định quan sát được.
2. Nhận các xung đột từ Người 1–3; xác định trường nào xung đột, các nguồn, quy tắc chọn nguồn và kết quả. Nếu chưa thể giải, giữ `selected_source: null` khi phù hợp và hạ confidence thay vì xóa xung đột.
3. Xếp hạng `root_cause_analysis.ranked_causes`, gán `responsible_parties` bằng ID và loại trách nhiệm hợp lệ. Đề xuất `assessment.primary_issue`, `secondary_issues`, `case_status`, confidence và `resolution_actions` nhất quán với findings và policy.
4. Kiểm tra `financial_resolution` cùng Người 3: chính sách áp dụng, số đã hoàn, số đề xuất hoàn, từng refund line và hành động tương ứng. Tránh đề xuất hoàn tiền trùng hoặc yêu cầu hành động khi `case_status` là `no_action`.
5. Xây dựng verifier độc lập: kiểm tra schema, entity scope, candidate bị loại, evidence refs thuộc đúng case/run/team theo dữ liệu có thể kiểm tra, claim–evidence linkage, timeline, tổng tiền, nguồn ưu tiên, trách nhiệm–hành động, confidence trong [0,1] và các trường bắt buộc.
6. Emit `verification_completed` trước khi Người 1 finalize; nếu fail, trả lỗi có cấu trúc cho agent sở hữu phần đó sửa, có giới hạn vòng lặp. Không tự thay dữ liệu sai bằng một giá trị hợp schema nhưng không có evidence.
7. Viết test module độc lập bằng ba `AgentResult` mẫu: nguồn đồng thuận, nguồn mâu thuẫn, không có policy evidence, refund đã thực hiện, draft có sai scope/ref/tổng tiền. Module phải chạy được khi ba module còn lại chưa hoàn thành.
8. **Sau khi tích hợp:** chạy `pytest -q`, `day09 validate`, rà soát trace; cập nhật `ARCHITECTURE.md` theo thiết kế thực tế (ownership, A2A, evidence/conflict, failure/efficiency, verification, reproducibility).
9. Chạy `day09 package --output dist/submission-v3.zip`; kiểm tra ZIP chỉ gồm `manifest.json`, `trace.jsonl`, `outputs/<case_id>.json`. Sau khi cả nhóm duyệt, thực hiện bước upload/chọn bản final trên workspace.

**Bàn giao độc lập:** module policy/decision/verifier, test và hướng dẫn hai điểm gọi của module. **Bàn giao sau khi gộp:** kiến trúc cập nhật, báo cáo validate và ZIP. **Xong khi:** module tự kiểm tra được draft mẫu; sau tích hợp không còn lỗi hard gate đã biết, đủ 100 output/trace hợp lệ.

## 4. Thứ tự phối hợp và điểm bàn giao

| Giai đoạn | Người chủ trì | Việc phải chốt/bàn giao | Điều kiện sang bước sau |
| --- | --- | --- | --- |
| 1. Chốt kiến trúc | Cả 4 người; Người 4 ghi tài liệu | Sơ đồ bốn module, owner, hợp đồng task/result, thứ tự gọi, quyền MCP, trace, lỗi và verifier trong `ARCHITECTURE.md` | Cả bốn người review, không còn giao diện chưa rõ |
| 2. Tạo hợp đồng chung | Người 1; cả nhóm review | `agent_contracts.py`, task/result mẫu, test kiểm tra hợp đồng | Bốn module có thể dùng cùng một kiểu dữ liệu |
| 3. Phát triển song song | Cả 4 người, mỗi người sở hữu một module | Mỗi module + test với gateway/task giả lập; review chéo ngay khi có bản bàn giao | Từng module chạy được khi các module khác chưa có và không còn lỗi hợp đồng chặn tích hợp |
| 4. Tích hợp | Người 1; Người 4 review | Gọi bốn module từ `solve_case()`, trace A2A, ghép output, verifier | Chạy được case đại diện, output và trace hợp lệ |
| 5. Kiểm thử và nộp | Người 4; cả nhóm duyệt | Chạy 100 case, validate, review thủ công, cập nhật kiến trúc theo thực tế, package | ZIP hợp lệ và được nhóm chọn để nộp |

### Checklist bàn giao cho mỗi phần

- [ ] Đầu vào và phạm vi `case_id` được ghi rõ.
- [ ] Module dùng đúng `AgentTask`/`AgentResult` đã chốt; không import module của người khác hoặc sửa `workflow.py` khi đang phát triển riêng.
- [ ] Kết luận có cấu trúc, không phụ thuộc vào lời giải thích tự do để agent khác sử dụng.
- [ ] Mọi ID, số tiền và quyết định quan trọng gắn với evidence refs đúng phạm vi.
- [ ] Trạng thái thiếu dữ liệu, mâu thuẫn và mức confidence được thể hiện rõ.
- [ ] Trace ghi đúng các sự kiện đã xảy ra; không ghi suy luận nội bộ hoặc bí mật.
- [ ] Có kiểm tra trên ít nhất một tình huống bình thường và một tình huống lỗi/mơ hồ thuộc phạm vi phụ trách.
- [ ] Module chạy độc lập bằng task/gateway giả lập; người review kiểm tra trước khi Người 1 tích hợp.

## 5. Tệp liên quan

| Tệp/thư mục | Mục đích |
| --- | --- |
| `README.md` | Hướng dẫn cuộc thi, cách chạy và nộp bài |
| `ARCHITECTURE.md` | Chốt kiến trúc mục tiêu trước khi code; cập nhật lại theo quyết định thực tế |
| `src/student_agent/agent_contracts.py` | Hợp đồng task/result chung đã triển khai; Người 1 sở hữu và bảo trì |
| `src/student_agent/agents/` | Bốn module agent đã triển khai; mỗi người sở hữu một module |
| `tests/test_agent_contracts.py` | Test hợp đồng chung đã triển khai |
| `tests/test_entity_customer.py`, `tests/test_order_fulfillment.py`, `tests/test_payment_refund.py`, `tests/test_policy_verifier.py` | Test độc lập của bốn module đã triển khai với fake gateway |
| `tests/test_workflow_integration.py` | Test tích hợp đã triển khai |
| `src/student_agent/workflow.py` | Điểm tích hợp `solve_case()` đã triển khai |
| `src/student_agent/mcp_gateway.py` | Kết nối MCP, khám phá tool và validate response |
| `src/student_agent/trace.py` | Ghi sự kiện trace theo schema |
| `src/student_agent/cli.py` | Chạy toàn bộ case, validate và gọi các bước CLI |
| `src/student_agent/submission.py` | Validate artifacts và tạo ZIP |
| `contracts/schemas/` và `contracts/scoring/` | Contract và tiêu chí chấm công khai |
| `tests/` | Kiểm thử starter và kiểm thử mới của nhóm |

## 6. Cây file làm việc đã tạo

Các file agent và `workflow.py` đã triển khai. Bốn người tiếp tục dùng checklist này để review chéo và cải thiện kết quả chấm.

```text
src/student_agent/
  agent_contracts.py          Người 1, cả nhóm review
  workflow.py                 Người 1 tích hợp sau cùng
  agents/
    __init__.py               Khai báo package
    entity_customer.py        Người 1
    order_fulfillment.py      Người 2
    payment_refund.py         Người 3
    policy_verifier.py        Người 4
tests/
  test_agent_contracts.py     Người 1
  test_entity_customer.py     Người 1
  test_order_fulfillment.py   Người 2
  test_payment_refund.py      Người 3
  test_policy_verifier.py     Người 4
  test_workflow_integration.py  Người 1, Người 4 review
phan-cong/
  NGUOI_1.md
  NGUOI_2.md
  NGUOI_3.md
  NGUOI_4.md
```
