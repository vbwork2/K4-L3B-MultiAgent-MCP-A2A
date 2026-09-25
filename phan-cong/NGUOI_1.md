# Người 1 — Entity/customer và tích hợp Coordinator

> Thành viên: _Điền tên_. Người review: Người 4. Các file module/test đã được tạo dưới dạng TODO; logic vẫn cần triển khai. Tài liệu chung của nhóm: [PHAN_CONG_CONG_VIEC.md](../PHAN_CONG_CONG_VIEC.md) và [ARCHITECTURE.md](../ARCHITECTURE.md).

## A. Thống nhất chung cho cả bốn người

### A1. Mục tiêu và thứ tự làm việc

- Bài toán là điều tra 100 case L3B bằng multi-agent, MCP evidence và trace A2A; kết quả cuối gồm 100 output JSON, trace JSONL và ZIP nộp bài.
- Trước khi viết logic, cả nhóm review và chốt ARCHITECTURE.md: ranh giới bốn module, AgentTask/AgentResult, quyền MCP theo miền, thứ tự gọi, cách ghi trace, xử lý lỗi và verifier.
- Người 1 tạo hợp đồng chung trong src/student_agent/agent_contracts.py sau khi chốt. Ngay khi hợp đồng và task/result mẫu đã được cả nhóm review, **cả bốn người bắt đầu module song song**; không chờ module khác hoàn thành. Người 2/3 dùng entity result mẫu, Người 4 dùng ba result mẫu để tự test. Người 1 ghép trong src/student_agent/workflow.py sau khi bốn module bàn giao.
- Bốn file module đã có trong src/student_agent/agents/: entity_customer.py, order_fulfillment.py, payment_refund.py, policy_verifier.py. Nội dung hiện chỉ là TODO; người phụ trách triển khai sau khi chốt hợp đồng chung.

### A2. Hợp đồng bàn giao giữa các module

- AgentTask tối thiểu mang case_id, sender, target, scope/ID đã xác minh, câu hỏi cần trả lời và query budget. AgentResult tối thiểu mang case_id, actor, status, findings có cấu trúc, evidence_refs, confidence, unresolved issues và errors có cấu trúc.
- Mọi module trả đúng case_id; không gọi trực tiếp module của người khác. Chỉ Coordinator trong workflow.py tạo task, chuyển result, ghép output và gọi verifier.
- Entity/customer xác định order trước. Order/fulfillment và payment/refund dùng cùng scope đã xác minh. Policy/verifier nhận ba kết quả, áp dụng policy, rồi kiểm tra draft output sau khi Coordinator ghép.
- Mỗi thay đổi của hợp đồng chung phải được cả bốn người review trước khi sửa module phụ thuộc. Không tự thêm field hoặc đổi nghĩa status ở riêng một module.

### A3. Quy tắc evidence, output và trace

- contracts/schemas/ và contracts/scoring/scoring-policy-v2.json là nguồn chuẩn. Input claim, candidate và customer hint chỉ là đầu mối, không phải evidence xác nhận khiếu nại.
- MCP tool do gateway cung cấp. Dùng tool discovery để biết tên tool thật; mỗi module chỉ gọi miền cần thiết qua EvidenceGateway, luôn truyền đúng case_id, không tự tạo/sửa evidence_ref, không dùng ref chéo case.
- Cache chỉ trong phạm vi case. Retry/query phải có giới hạn do nhóm chốt; mọi MCP call được audit và ảnh hưởng efficiency, kể cả call không dùng trong output.
- Khi dùng evidence, ghi tool_result_consumed với actor, tool và refs. Coordinator ghi task_assigned/handoff; policy agent ghi policy_decided; verifier ghi verification_completed. CLI đã ghi case_received và case_finalized, không ghi trùng.
- Không đủ chứng cứ thì trả trạng thái thiếu chứng cứ hoặc mơ hồ phù hợp; ghi xung đột nguồn thay vì đoán. Mọi claim, số tiền, trách nhiệm và hành động cần truy về evidence.
- Không ghi prompt, chain-of-thought, API key vào trace/output. Không commit .env, input thi đấu, output, trace, ZIP hoặc log. Comment trong code bằng tiếng Anh dễ hiểu; không dùng icon trong code.

### A4. Điều kiện chung để gộp và nộp

- Mỗi người bàn giao module, test với gateway/task giả lập, result mẫu, các miền MCP cần dùng và giới hạn đã biết. Người review kiểm tra **song song với quá trình hoàn thiện module** và chốt các lỗi giao diện trước khi gộp; review không phải bước chặn để ba người khác bắt đầu làm.
- Sau khi gộp: chạy day09 validate-inputs, python -m pytest -q, day09 run, day09 validate và day09 package --output dist/submission.zip; kiểm tra đủ 100 case và ZIP đúng cấu trúc.
- Ưu tiên tránh hard gate: sai case_id, schema không chấm được, thiếu evidence bắt buộc, ref không tồn tại hoặc sai team/run/case. Cập nhật ARCHITECTURE.md khi thiết kế thực tế thay đổi.

## B. Phần việc riêng của Người 1

### B1. Phạm vi sở hữu

- Module chính: src/student_agent/agents/entity_customer.py. Chức năng là xác định order và customer đúng, loại candidate sai, lấy customer history theo investigation_scope.
- File test riêng: tests/test_entity_customer.py. File test tích hợp sau khi gộp: tests/test_workflow_integration.py.
- Phần dùng chung phụ trách tạo bản đầu: src/student_agent/agent_contracts.py, sau khi cả nhóm chốt interface.
- File test hợp đồng chung: tests/test_agent_contracts.py.
- Phần tích hợp cuối cùng: src/student_agent/workflow.py. Chỉ bắt đầu ghép khi bốn module có test độc lập; không đưa logic chuyên môn của ba người khác vào workflow.py.
- Người review module và tích hợp: Người 4.

### B2. Đầu vào và đầu ra của module

- Đầu vào: AgentTask của Coordinator, case gồm case_id, opened_at, customer_request, candidate_order_ids, customer_unique_id_hint, investigation_scope và policy_version; EvidenceGateway và TraceWriter dùng chung.
- Đầu ra: AgentResult chứa entity_resolution.status, resolved_order_ids, rejected_candidates, confidence, customer_context, ID/scope hợp lệ cho các module sau, evidence_refs và unresolved issues.
- Nếu ambiguous hoặc not_found, trả trạng thái rõ ràng và phạm vi đã thực sự xác minh; không chọn bừa claimed_order_id để các module sau tiếp tục.

### B3. Việc cần làm

1. Cùng nhóm chốt sơ đồ, tên actor, AgentTask/AgentResult, status, confidence, query budget, mã lỗi, cách ghi trace và mapping output; ghi vào ARCHITECTURE.md.
2. Tạo agent_contracts.py và task/result mẫu. Nhờ cả ba người còn lại review kiểu dữ liệu trước khi họ viết module.
3. Khám phá MCP tool thuộc miền order/customer; xác định truy vấn tối thiểu để kiểm tra claimed order, các candidate và customer hint. Ghi nguyên evidence_ref của kết quả dùng.
4. Xếp hạng và loại candidate bằng các thuộc tính có chứng cứ; tách đơn của khách hàng có liên quan khỏi đơn đang khiếu nại. Trả resolved, ambiguous hoặc not_found đúng tình huống.
5. Khi include_customer_history bật, lấy lịch sử khách hàng và điền customer_unique_id, related_order_ids. Không lấy lịch sử rộng nếu scope không yêu cầu.
6. Viết test module với gateway giả lập: candidate đúng, candidate sai, hai candidate gần nhau, không tìm thấy, customer hint sai và MCP timeout.
7. Sau bàn giao của cả nhóm, viết Coordinator: tạo task, gọi entity trước, chuyển scope cho Người 2/3, gọi Người 4, ghép mọi trường L3B output, gọi verifier, ghi task_assigned/handoff và trả output đã được chấp nhận.
8. Kiểm tra không phát trùng case_received/case_finalized vì CLI đã ghi hai sự kiện đó.

### B4. Bàn giao và tự kiểm tra

- Bàn giao sớm: agent_contracts.py, task/result mẫu và quyết định kiến trúc đã review.
- Bàn giao module: entity_customer.py, test, ví dụ AgentResult cho resolved/ambiguous/not_found, danh sách MCP tool thực dùng và các lỗi còn mở.
- Bàn giao sau gộp: workflow.py và bản mapping từng findings sang output schema.
- Hoàn thành khi module chạy được độc lập; không chọn sai candidate; scope chuyển cho Người 2/3 có evidence; draft chỉ được trả sau verifier; output đúng case_id và schema.
