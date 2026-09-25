# L3B Architecture Record

> **Trạng thái: đã triển khai theo thiết kế.** Bốn module agent, hợp đồng bàn giao, Coordinator, verifier, cache evidence theo case và CLI chạy/đóng gói đã có trong code. Nhóm vẫn cần review nghiệp vụ và điều chỉnh khi có kết quả chấm thực tế. Không ghi prompt bí mật, chain-of-thought hoặc API key.

Xem [PHAN_CONG_CONG_VIEC.md](PHAN_CONG_CONG_VIEC.md) để biết người sở hữu từng module, đầu việc và thứ tự bàn giao.

## 1. System overview

```text
CLI -> workflow.py / Coordinator
          |
          +-> entity_customer.py -> EntityResult
          |                         |
          +-> order_fulfillment.py <-+
          +-> payment_refund.py    <-+
          |          |               |
          +-> policy_verifier.py  <--+ (policy, conflicts, decision)
          |
          +-> draft L3B output -> policy_verifier.verify -> final output
          |
          +-> TraceWriter

Mọi module chỉ gọi MCP qua EvidenceGateway và nhận task/result theo agent_contracts.py.
```

`src/student_agent/workflow.py` giữ chữ ký `async def solve_case(case, gateway, trace) -> dict`. Coordinator gọi các module, ghi sự kiện bàn giao, ghép output và chỉ trả về sau khi verifier chấp nhận. Hai module order/fulfillment và payment/refund không phụ thuộc nhau; có thể chạy đồng thời sau entity resolution nếu bảo đảm trace và ngân sách MCP vẫn nhất quán. Bản đầu nên chạy tuần tự để dễ kiểm chứng.

## 2. Agent ownership và quyền dùng tool

| Actor/module dự kiến | Input | Trách nhiệm | Miền MCP được phép truy vấn | Output/handoff |
| --- | --- | --- | --- | --- |
| `entity-customer` / `agents/entity_customer.py` | Case và candidate/hint | Xác minh order/customer, loại candidate, lấy customer context | `order`, `customer`; chỉ bổ sung miền khác khi có lý do và cả nhóm chốt | EntityResult cho Coordinator |
| `order-fulfillment` / `agents/order_fulfillment.py` | Case và order scope đã xác minh | Kiểm tra order/item/seller/product, dựng shipment timeline | `order`, `item`, `seller`, `product`, `shipment` | FulfillmentResult cho Coordinator |
| `payment-refund` / `agents/payment_refund.py` | Case và order scope đã xác minh | Đối soát capture, split payment, refund và số tiền | `payment`, `refund` | FinanceResult cho Coordinator |
| `policy-verifier` / `agents/policy_verifier.py` | Ba kết quả chuyên môn, sau đó draft output | Áp dụng policy, xử lý conflict, đề xuất quyết định và kiểm chứng draft | `policy`; đọc evidence refs/findings đã bàn giao | DecisionResult và VerificationResult |
| `coordinator` / `workflow.py` | Case, gateway, trace và mọi result | Lập task, kiểm soát thứ tự, ghép output, finalize | Không truy vấn miền nghiệp vụ thay agent; chỉ điều phối gateway dùng chung | L3B output |

Mỗi người sở hữu một module agent. `agent_contracts.py` là hợp đồng chung, do Người 1 tạo bản đầu sau khi cả nhóm review. Tên MCP tool cụ thể phải lấy bằng `gateway.list_tools()`/`day09 mcp-tools`; bảng chỉ định **miền dữ liệu**, không đoán tên tool trước discovery. Tool discovery không tự cấp quyền gọi mọi tool cho mọi actor.

Sau khi chốt hợp đồng chung, bốn module được phát triển **song song**. Người 2/3 dùng EntityResult mẫu; Người 4 dùng ba AgentResult mẫu; Người 1 test entity độc lập. Review chéo diễn ra khi từng module có bản bàn giao và không chặn các module khác tiếp tục phát triển. Coordinator chỉ tích hợp module đã qua review về interface và hành vi thiết yếu; cả nhóm kiểm tra luồng cuối sau khi ghép.

## 3. Entity resolution và A2A protocol

**Hợp đồng nội bộ cần chốt và mã hóa trong `agent_contracts.py`:**

| Cấu trúc | Trường tối thiểu | Quy tắc |
| --- | --- | --- |
| `AgentTask` | `case_id`, `sender`, `target`, `scope`, `questions`, `query_budget` | `case_id` phải trùng case gốc; scope chỉ chứa ID đã có căn cứ |
| `AgentResult` | `case_id`, `actor`, `status`, `findings`, `evidence_refs`, `confidence`, `unresolved`, `errors` | Result không được đổi `case_id`; refs là chuỗi do MCP cấp; lỗi có cấu trúc |
| `VerificationResult` | `case_id`, `passed`, `issues` | Mỗi issue nêu field, lý do, module cần sửa; không âm thầm vá dữ liệu |

Tên trường và kiểu cụ thể đã được mã hóa trong `agent_contracts.py`. Message envelope dùng trong tiến trình Python qua Coordinator; không cần giả định có A2A server ngoài repo. Coordinator là nơi duy nhất tạo task cho agent khác, kiểm tra result, phát `task_assigned`/`handoff` và ngăn vòng lặp bàn giao. Khi thay đổi hợp đồng, cả bốn người cần review trước khi gộp.

Entity resolver kiểm tra `claimed_order_id`, candidate và customer hint với evidence; ghi candidate được nhận, bị loại và confidence. Khi cùng một order ID xuất hiện ở nhiều thời kỳ, nó chọn bản ghi mua hàng phù hợp với thời điểm mở case và bàn giao mốc mua kế tiếp để các agent khác lọc dữ liệu. Nếu `not_found`, Coordinator không tự chọn order. Confidence hiện là mức heuristic trong từng module, chưa phải xác suất đã hiệu chuẩn từ tập chấm công khai.

## 4. Evidence và conflict lifecycle

1. Gateway validate MCP evidence response; agent luôn truyền `case_id` của task khi gọi tool và chỉ tiêu thụ evidence trong phạm vi case hiện tại. Evidence envelope công khai không có trường `case_id`, nên không suy ra ownership chỉ từ response; provenance cuối cùng phải khớp audit của server.
2. Cache theo khóa `(case_id, tool_name, arguments)` trong một lần xử lý case; không chia sẻ evidence giữa các case. Lưu `evidence_ref` nguyên bản cùng claim/finding sử dụng nó.
3. Khi dùng evidence, agent phát `tool_result_consumed` gồm actor, tool name, refs. Coordinator chỉ gộp refs liên quan vào output, không tự chế hoặc sửa refs.
4. Agent phát hiện xung đột phải bàn giao field, các giá trị/nguồn và refs. `policy-verifier` áp dụng quy tắc ưu tiên nguồn đã chốt, ghi `data_conflicts`; nếu chưa giải được thì để `selected_source` là `null` khi phù hợp và giảm confidence.
5. `claim_assessments`, root cause, financial resolution và action phải truy ngược được đến findings và evidence; input claim/hint không được xem là evidence.

## 5. Failure and efficiency policy

| Failure | Hành vi dự kiến | Fallback và trace |
| --- | --- | --- |
| MCP timeout/lỗi tạm thời | Retry hữu hạn theo ngân sách chung; không gọi vô hạn | Trả lỗi có cấu trúc; hạ confidence hoặc `needs_investigation` khi thiếu evidence |
| Entity không tìm thấy/mơ hồ | Không suy diễn order từ hint | `not_found`/`ambiguous`; chỉ điều tra scope có căn cứ |
| Source conflict | Gửi conflict đến `policy-verifier` | Ghi `data_conflicts`; không che mâu thuẫn bằng một giá trị tùy ý |
| Specialist result sai hợp đồng | Coordinator từ chối result và trả issue cho module sở hữu | Trace handoff/lỗi quan sát được; giới hạn vòng sửa |
| Verifier từ chối draft | Sửa đúng module/field liên quan, chạy lại kiểm tra | Không finalize output chưa được kiểm chứng |

`CaseEvidenceGateway` có cache và bộ đếm theo case; quyền tool được giới hạn theo từng actor. Chưa đặt trần call cứng vì scoring policy giữ kín mức tối ưu; các nhánh chỉ gọi tool cần cho topic và scope. `run_submission.cmd` chạy 2 case song song, mở lại kết nối MCP sau mỗi nhóm 16 case và ghi output/trace ngay khi từng case xong. Lượt đầu chạy mới; chỉ retry trong cùng lượt mới dùng `--resume`. Resume kiểm tra fingerprint của input, endpoint và Team API Key để chặn việc trộn ref giữa hai ngữ cảnh. Mọi MCP call được server audit và có thể ảnh hưởng điểm efficiency, kể cả call không xuất hiện trong output.

Payment agent đối chiếu các capture với dòng thanh toán trong `get_payment_timeline`. Thử nghiệm v3 gọi thêm `get_order_payments` cho ba nhóm payment làm điểm hiệu quả giảm mạnh nhưng evidence coverage chỉ tăng nhẹ, vì vậy v4 bỏ lời gọi này. Khi cùng một order ID có nhiều lần mua trước khi mở case, entity agent ưu tiên bản ghi lịch sử có trạng thái khớp với claim hủy đơn hoặc hết hàng nếu bản ghi đó tồn tại; các tool tiếp theo được giới hạn theo khoảng thời gian của lần mua đã chọn.

Ở v5, `policy-verifier` gắn evidence cho từng claim theo sự kiện cần chứng minh: claim hoàn toàn bộ tiền nhận cả chứng cứ về nguyên nhân hoàn và về số tiền; claim có trách nhiệm seller nhận seller ref nếu đã được thu thập. Thay đổi này không phát sinh MCP call, còn output cấp case giữ toàn bộ refs đã dùng để verifier đối chiếu với trace.

## 6. Verification invariants

Verifier kiểm tra tối thiểu: output đúng L3B schema và `case_id`; entity/order scope; rejected candidates không lọt vào affected entities; các ref có nguồn gốc từ evidence đã dùng trong cùng case; claim–evidence linkage; timeline và shipment verdict; capture/refund totals; tổng refund lines và số đề xuất; source precedence; trách nhiệm và action không mâu thuẫn; confidence trong [0,1]. Kiểm tra các hard gate công khai trước: `case_id_mismatch`, `unscorable_schema`, `missing_required_evidence`, `invalid_evidence_refs`, `unknown_evidence_ref`, `cross_scope_evidence_ref`.

`workflow.py` chỉ ghi `verification_completed` sau khi thực sự gọi verifier. CLI đã ghi `case_received` và `case_finalized`; không ghi trùng. Trace chỉ chứa sự kiện quan sát được, không chứa nội dung suy luận nội bộ.

Hàm verifier nằm cùng module do Người 4 sở hữu để giữ đúng bốn phần phát triển độc lập, nhưng phải là một bước kiểm tra riêng trên **draft đã ghép**, dùng quy tắc xác minh và test riêng; không đơn thuần trả lại kết quả policy/decision vừa tạo.

## 7. Reproducibility và điều kiện gộp

- Dùng Python >= 3.11 và dependency trong `pyproject.toml`. Ghi cấu hình model (nếu dùng), giới hạn đồng thời, random seed (nếu có), retry/query budget và lệnh chạy thực tế; không ghi secret.
- Trước khi gộp, mỗi người bàn giao module, test với gateway/task giả lập, result mẫu, danh sách MCP domain cần dùng và các tình huống chưa xử lý.
- Sau khi gộp, chạy `day09 validate-inputs`, `pytest -q`, `day09 run`, `day09 validate`, rồi `day09 package --output dist/submission-v5.zip`; kiểm tra đủ 100 case và ZIP chỉ chứa manifest, trace, outputs.
- Cập nhật bảng và các quyết định ở tài liệu này nếu code cuối cùng khác thiết kế đề xuất. Thay đổi hợp đồng task/result phải được cả nhóm review trước khi sửa module phụ thuộc.
