# Người 3 — Payment và refund

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

## B. Phần việc riêng của Người 3

### B1. Phạm vi sở hữu

- Module chính: src/student_agent/agents/payment_refund.py. Chức năng là đối soát capture/payment/refund theo order đã xác minh và tính các tổng BRL làm căn cứ quyết định.
- File test riêng: tests/test_payment_refund.py.
- Không tự gán nguyên nhân vận chuyển hoặc tự chọn chính sách; Người 4 tính quyết định hoàn tiền cuối cùng từ findings tài chính và policy.
- Người review: Người 4.

### B2. Đầu vào và đầu ra của module

- Đầu vào: AgentTask chứa case_id, order scope đã xác minh, claim tài chính và query budget; EvidenceGateway và TraceWriter dùng chung.
- Đầu ra: AgentResult chứa payment_references, danh sách giao dịch có trạng thái/số tiền, payment_analysis.verdict, captured_total_brl, refunded_total_brl, refundable_total_brl, claim verdict đề xuất, evidence_refs và conflict/unresolved issues.
- Phân biệt số 0 được evidence chứng minh với null do thiếu dữ liệu; không cộng trùng giao dịch hoặc refund.

### B3. Việc cần làm

1. Review ARCHITECTURE.md và agent_contracts.py; xác nhận cách nhận order scope, biểu diễn số tiền/thiếu dữ liệu và bàn giao refs.
2. Khám phá MCP tool miền payment/refund; chọn truy vấn tối thiểu theo order và claim, luôn truyền đúng case_id.
3. Tái dựng các lần capture, phương thức thanh toán, split payment, refund đã thực hiện/đang chờ/thất bại. Liên kết từng payment reference với order đã xác minh.
4. Đối soát tổng capture với nghĩa vụ thanh toán; phân biệt split payment hợp lệ với duplicate_capture và capture_mismatch.
5. Tính captured_total_brl, refunded_total_brl và refundable_total_brl có căn cứ. Xử lý refund từng phần, nhiều giao dịch, dữ liệu thiếu và sai khác giữa payment/refund sources.
6. Chọn payment_analysis.verdict theo enum schema: reconciled, capture_mismatch, duplicate_capture, refund_pending, refund_failed, refunded hoặc insufficient_evidence. Không chọn verdict chỉ để khớp claim.
7. Bàn giao bảng đối soát và claim verdict có refs cho Người 4; phối hợp kiểm tra recommended_refund_brl và refund_lines sau khi policy được áp dụng, tránh hoàn trùng hoặc vượt phần đủ điều kiện.
8. Viết test với task entity mẫu và gateway giả lập: split payment hợp lệ, capture trùng, capture lệch, refund một phần, refund failed, refunded và thiếu số tiền.

### B4. Bàn giao và tự kiểm tra

- Bàn giao payment_refund.py, test, bảng đối soát mẫu, AgentResult mẫu, danh sách MCP tool đã dùng và các giả định về tiền tệ/làm tròn đã được nhóm chốt.
- Module phải import/chạy được khi order_fulfillment.py và policy_verifier.py chưa hoàn thành.
- Hoàn thành khi các tổng không đếm trùng; split payment hợp lệ không bị xem là gian lận; null và 0 được dùng đúng; mỗi kết luận tài chính có evidence refs đúng case.
