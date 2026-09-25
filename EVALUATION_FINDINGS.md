# Phân tích điểm và phiên v4

## Kết quả đã biết

| Phiên | Điểm trang chấm | MCP call | Nhận xét |
| --- | ---: | ---: | --- |
| v2 | 89.5123 | 740 | Mốc cao nhất đã được người dùng xác nhận. |
| v3 | 89.2991 | 770 | Gọi thêm `get_order_payments` cho 30 case; evidence coverage tăng 84.57 lên 84.87, nhưng hiệu quả tool call giảm 72.23 xuống 67.22. |
| v4 | 89.9559 | 740 | Bỏ call bổ sung của v3 và sửa lỗi chọn lần mua ở case 098. |
| v5 | Chưa có điểm trang chấm | Dự kiến 740 | Giữ quyết định của v4; gắn thêm chứng cứ nguyên nhân vào claim hoàn tiền và chứng cứ seller vào claim liên quan. |

Không thể bảo đảm điểm riêng tư cao hơn trước khi tải ZIP lên trang chấm. Các kiểm tra dưới đây xác nhận đầu ra hợp lệ và phạm vi thay đổi, không thay thế kết quả của trang chấm.

## Lỗi được xác minh

`L3B_CASE_098` có hai lần mua cùng `order_id` trước thời điểm mở case. `get_customer_history` ghi lần mua 05/08 đã hủy và lần mua 14/08 đã giao. Claim `canceled_order_paid` thuộc lần mua 05/08. Dữ liệu MCP ghi capture 79 BRL ngày 05/08 và capture 18 BRL ngày 14/08; các item và mốc giao hàng cũng thuộc hai khoảng thời gian khác nhau.

V2/v3 luôn lấy lần mua gần nhất, vì thế lấy lần 14/08, kết luận `unsupported_claim`, ghi nhận 18 BRL và đề xuất hoàn 0. V4 chỉ ưu tiên bản ghi lịch sử có trạng thái `canceled` hoặc `unavailable` khi claim tương ứng và bản ghi đó thực sự tồn tại. Sau đó các agent còn lại lọc dữ liệu theo khoảng từ lần mua được chọn đến lần mua tiếp theo. Case 098 nay kết luận `canceled_order_paid`, ghi nhận 79 BRL, đề xuất hoàn 79 BRL và ghi xung đột timestamp giữa `customer_history` và `get_order`.

## Kiểm tra phiên v4

- 19 unit tests pass; Ruff pass; `git diff --check` pass.
- `run_submission.cmd` chạy mới 100/100 case; `day09 validate` pass.
- ZIP chứa 100 output, `trace.jsonl`, `manifest.json`; trace có 1.940 event, trong đó 740 `tool_result_consumed`, 400 `task_assigned`, 400 `handoff`, 100 `verification_completed` và 100 `case_finalized`.
- So với v2, sau khi bỏ các evidence ref mới theo phiên, chỉ output của case 098 thay đổi. 99 case còn lại giữ nguyên nội dung quyết định.
- Không có evidence ref trùng giữa ZIP v3 và v4; phiên v4 dùng lượt MCP mới với cùng input.

## Chiến thuật v5 từ điểm các phiên trước

V3 so với v2: evidence coverage tăng 0.30 điểm thành phần, nhưng hiệu quả tool call giảm 5.01. Theo trọng số 15% và 5%, tác động xấp xỉ `+0.045 - 0.2505`, giải thích phần lớn mức giảm 0.2132 điểm tổng. Vì vậy không thêm MCP call theo nhóm khi lợi ích evidence chưa được chứng minh.

V4 so với v2: semantic tăng 1.09 và calibration tăng 0.88 điểm thành phần sau khi sửa đúng một case. Tác động có trọng số xấp xỉ `+0.436 + 0.044`, lớn hơn hẳn biến động nhỏ của các thành phần khác. Vì vậy tiếp tục ưu tiên lỗi scope hoặc chứng cứ làm sai kết luận. Trước thử nghiệm v5, cả 100 case v4 đều có `primary_issue` phù hợp với nhóm input; chưa tìm được một case sai rõ ràng khác để sửa semantic mà không tăng rủi ro.

V5 tập trung vào evidence linkage với cùng 740 MCP call: claim `requested_full_refund` nhận cả chứng cứ xác lập nguyên nhân hoàn tiền từ claim chính và chứng cứ về số tiền. Claim giao trễ do seller hoặc đơn unavailable nhận ref seller đã gọi sẵn. Product ref vẫn ở danh sách bằng chứng của case vì input yêu cầu product context, nhưng không được gắn vào claim khi dữ liệu product category không tham gia kết luận. Thử nghiệm này có rủi ro precision giảm nếu trang chấm coi một nguồn nguyên nhân là thừa; cần đối chiếu điểm evidence của v5 với 84.59 ở v4 và giữ ZIP v4 làm mốc an toàn.

Phiên v5 đã chạy đủ 100 case. Lần chạy bị lỗi đọc kết nối sau 63 case; `resume` tiếp tục đúng 37 case còn lại. ZIP có 100 output và 1.940 trace event; 740 refs trong output đều xuất hiện trong trace của đúng case, không trùng refs v4. Sau khi chuẩn hóa evidence refs theo phiên, 100/100 kết luận và số tiền giống v4. Thay đổi chỉ ở liên kết chứng cứ: 80 claim hoàn tiền và 20 claim chính thuộc nhóm seller/unavailable nhận thêm refs đã có; 20 claim hoàn tiền thuộc nhóm refund không đổi.

Quy tắc chọn bản nộp: nếu điểm tổng v5 cao hơn 89.9559 và evidence coverage cao hơn 84.59, giữ v5. Nếu điểm evidence giảm hoặc điểm tổng không tăng, dùng lại ZIP v4 đã chấm và phân tích nhóm refs thêm trước thử nghiệm tiếp theo. Không bỏ `get_product_context` ở v5 vì input yêu cầu scope này; muốn giảm call cần một thử nghiệm riêng, do rủi ro mất required evidence.

File nộp v4: `dist/submission-v4.zip`. File v5 sau khi chạy: `dist/submission-v5.zip`. Chỉ điểm trang chấm sau khi tải file mới lên mới xác nhận mức cải thiện thực tế.
