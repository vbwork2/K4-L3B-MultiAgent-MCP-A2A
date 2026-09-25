# Người 4 — Policy, conflict và verifier

> Thành viên: _Điền tên_. Người review: Người 2. Module đã có bản triển khai chung trong repo; người phụ trách tiếp tục kiểm thử nghiệp vụ, review chéo và cải tiến theo kết quả chấm. Tài liệu chung của nhóm: [PHAN_CONG_CONG_VIEC.md](../PHAN_CONG_CONG_VIEC.md) và [ARCHITECTURE.md](../ARCHITECTURE.md).

## A. Thống nhất chung cho cả bốn người

### A1. Mục tiêu và thứ tự làm việc

- Bài toán là điều tra 100 case L3B bằng multi-agent, MCP evidence và trace A2A; kết quả cuối gồm 100 output JSON, trace JSONL và ZIP nộp bài.
- Trước khi viết logic, cả nhóm review và chốt ARCHITECTURE.md: ranh giới bốn module, AgentTask/AgentResult, quyền MCP theo miền, thứ tự gọi, cách ghi trace, xử lý lỗi và verifier.
- Người 1 tạo hợp đồng chung trong src/student_agent/agent_contracts.py sau khi chốt. Ngay khi hợp đồng và task/result mẫu đã được cả nhóm review, **cả bốn người bắt đầu module song song**; không chờ module khác hoàn thành. Người 2/3 dùng entity result mẫu, Người 4 dùng ba result mẫu để tự test. Người 1 ghép trong src/student_agent/workflow.py sau khi bốn module bàn giao.
- Bốn file module đã có trong src/student_agent/agents/: entity_customer.py, order_fulfillment.py, payment_refund.py, policy_verifier.py. Mỗi người sở hữu một module để kiểm thử và cải tiến độc lập trên hợp đồng chung.

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
- Sau khi gộp: chạy day09 validate-inputs, python -m pytest -q, day09 run, day09 validate và day09 package --output dist/submission-v3.zip; kiểm tra đủ 100 case và ZIP đúng cấu trúc.
- Ưu tiên tránh hard gate: sai case_id, schema không chấm được, thiếu evidence bắt buộc, ref không tồn tại hoặc sai team/run/case. Cập nhật ARCHITECTURE.md khi thiết kế thực tế thay đổi.

## B. Phần việc riêng của Người 4

### B1. Phạm vi sở hữu

- Module chính: src/student_agent/agents/policy_verifier.py. Module có hai điểm gọi riêng: tạo decision từ ba AgentResult và verify draft output sau khi Coordinator ghép.
- File test riêng: tests/test_policy_verifier.py; cùng Người 1 review tests/test_workflow_integration.py sau khi gộp.
- Chức năng là áp dụng policy đúng version, giải quyết xung đột nguồn, xác định root cause/trách nhiệm/hành động/hoàn tiền, rồi kiểm tra đầu ra độc lập bằng các invariant.
- Phụ trách ghi ARCHITECTURE.md theo quyết định của cả nhóm và điều phối kiểm thử, đóng gói sau khi gộp. Người review module: Người 2.

### B2. Đầu vào và đầu ra của module

- Đầu vào decision: AgentTask, kết quả entity/customer, order/fulfillment, payment/refund, policy_version, EvidenceGateway và TraceWriter.
- Đầu ra decision: AgentResult chứa policy findings, data_conflicts, root_cause_analysis, assessment đề xuất, financial_resolution, resolution_actions, evidence_refs và unresolved issues.
- Đầu vào verifier: draft L3B output và provenance/AgentResult dùng để tạo draft. Đầu ra VerificationResult gồm passed và danh sách issue có field, lý do, module cần sửa.
- Verifier là bước kiểm tra riêng trên draft đã ghép; không đơn thuần xác nhận lại quyết định mà chính module vừa đưa ra.

### B3. Việc cần làm

1. Cùng cả nhóm chốt kiến trúc trước khi code; ghi ranh giới module, task/result, actor/trace, tool permission, lỗi/retry/query budget, source precedence, verifier và điều kiện gộp vào ARCHITECTURE.md.
2. Khám phá MCP tool miền policy; tra đúng policy_version của case. Không tự giả định nội dung chính sách từ tên version.
3. Nhận findings/conflict từ ba module, so sánh nguồn, chọn nguồn theo quy tắc đã chốt; nếu chưa thể giải, ghi data_conflicts với selected_source null khi phù hợp và hạ confidence.
4. Xếp hạng root_cause_analysis.ranked_causes, gán responsible_parties đúng loại và ID; đề xuất assessment.primary_issue, secondary_issues, case_status, confidence và resolution_actions phù hợp evidence.
5. Phối hợp Người 3 xác định financial_resolution.recommended_refund_brl và refund_lines từ policy, captured/refunded/refundable totals; tránh đề xuất hoàn tiền đã thực hiện hoặc vượt phần có thể hoàn.
6. Viết verifier kiểm tra schema, case_id, entity scope, rejected candidates, evidence refs, claim linkage, timeline, payment/refund totals, refund lines, source precedence, trách nhiệm/action và confidence. Trả issue có cấu trúc, không tự sửa dữ liệu không có evidence.
7. Emit policy_decided khi thật sự ra quyết định và verification_completed khi thật sự kiểm chứng. Nếu verify fail, trả lỗi cho Coordinator để giao đúng module sửa với số vòng hữu hạn.
8. Test module với ba AgentResult mẫu và draft mẫu: nguồn đồng thuận, nguồn mâu thuẫn, thiếu policy evidence, refund đã thực hiện, ref sai case, tổng tiền sai và action mâu thuẫn.
9. Sau khi gộp, chạy test/validate trên case đại diện và đủ 100 case, review trace; cập nhật ARCHITECTURE.md theo code thực tế và tạo dist/submission-v3.zip. Nhóm cùng duyệt trước khi chọn bản nộp cuối.

### B4. Bàn giao và tự kiểm tra

- Bàn giao policy_verifier.py, test cho decision và verifier, AgentResult/VerificationResult mẫu, quy tắc nguồn và policy tool đã dùng.
- Module phải kiểm thử được bằng ba result mẫu khi ba module còn lại chưa hoàn thành.
- Hoàn thành khi quyết định truy được về policy/evidence; conflict không bị che; verifier phát hiện lỗi cross-field quan trọng; sau tích hợp đủ 100 output/trace hợp lệ và ZIP chỉ có manifest, trace, outputs.
