# Người 2 — Order, product và shipment

> Thành viên: _Điền tên_. Người review: Người 1. Các file module/test đã được tạo dưới dạng TODO; logic vẫn cần triển khai. Tài liệu chung của nhóm: [PHAN_CONG_CONG_VIEC.md](../PHAN_CONG_CONG_VIEC.md) và [ARCHITECTURE.md](../ARCHITECTURE.md).

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

## B. Phần việc riêng của Người 2

### B1. Phạm vi sở hữu

- Module chính: src/student_agent/agents/order_fulfillment.py. Chức năng là xác minh order/item/seller/product và phân tích timeline vận chuyển.
- File test riêng: tests/test_order_fulfillment.py.
- Không tự resolve lại order đã được Người 1 xác minh; nếu scope không đủ chắc, trả unresolved issue để Coordinator quyết định.
- Không tính refund hoặc kết luận policy; bàn giao findings để Người 4 đối chiếu với tài chính và chính sách.
- Người review: Người 1.

### B2. Đầu vào và đầu ra của module

- Đầu vào: AgentTask chứa case_id, order scope do entity/customer xác minh, claim liên quan, investigation_scope và query budget; EvidenceGateway và TraceWriter dùng chung.
- Đầu ra: AgentResult chứa order/item/seller/product findings, affected order_ids/item_ids/seller_ids/shipment_ids, shipment_analysis.verdict, late_seller_ids, timeline_complete, claim verdict đề xuất, evidence_refs và conflict/unresolved issues.
- Timeline phải ghi rõ các mốc có evidence và mốc còn thiếu; verdict không được suy ra chỉ từ lời khiếu nại.

### B3. Việc cần làm

1. Review ARCHITECTURE.md và agent_contracts.py; xác nhận module nhận đúng scope và trả result theo hợp đồng chung.
2. Khám phá MCP tool miền order, item, seller, product, shipment; ghi lại tool/tham số cần cho từng loại claim, tránh quét mọi tool.
3. Kiểm tra trạng thái order, item, seller và product; xác định hủy đơn, thiếu hàng, sản phẩm không khớp hoặc các trường hợp seller chịu trách nhiệm dựa trên evidence.
4. Chỉ lấy product context khi include_product_context bật hoặc cần trực tiếp để xác minh claim. Trả đúng ID thuộc order đã xác minh; không đưa candidate bị loại vào affected_entities.
5. Dựng timeline từ các mốc seller bàn giao, vận chuyển, hẹn giao, giao thực tế, thất lạc và hoàn trả nếu có. So sánh thời gian trước khi chọn on_time, seller_delay, logistics_delay, lost, returned, conflicting hoặc insufficient_evidence.
6. Chỉ ghi late_seller_ids khi có đủ căn cứ quy trách nhiệm seller; đặt timeline_complete theo dữ liệu thực tế. Ghi conflict nếu hai nguồn cho mốc/trạng thái khác nhau.
7. Đánh giá claim về order/product/shipment, kèm verdict đề xuất, confidence và refs riêng. Bàn giao cho Coordinator và Người 4; không tự ghi mức hoàn tiền.
8. Viết test với task entity mẫu và gateway giả lập: giao đúng hạn, seller delay, logistics delay, timeline thiếu, item/seller không khớp và nguồn xung đột.

### B4. Bàn giao và tự kiểm tra

- Bàn giao order_fulfillment.py, test, task/result mẫu, timeline minh họa, danh sách MCP tool đã dùng và trường hợp chưa xử lý.
- Module phải import/chạy được khi payment_refund.py và policy_verifier.py chưa hoàn thành.
- Hoàn thành khi mọi ID nằm trong order scope; timeline và verdict khớp evidence; seller delay không bị nhầm với logistics delay; result đúng hợp đồng và đúng case_id.
