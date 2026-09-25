# Đề xuất kiến trúc thư mục L3B Multi-Agent MCP + A2A

Tài liệu này mô tả cấu trúc thư mục đề xuất để team review trước khi triển khai. Kiến trúc tập trung vào việc tách rõ phần điều phối, nghiệp vụ, quản lý bằng chứng và kiểm soát kết quả.

## 1. Cấu trúc thư mục

```text
K4-L3B-MultiAgent-MCP-A2A/
|
|-- src/
|   `-- student_agent/
|       |-- __init__.py
|       |-- cli.py
|       |-- config.py
|       |-- cases.py
|       |-- contracts.py
|       |-- trace.py
|       |-- submission.py
|       |-- mcp_gateway.py
|       |-- workflow.py
|       |
|       |-- core/
|       |   |-- __init__.py
|       |   |-- context.py
|       |   |-- messages.py
|       |   |-- agent_result.py
|       |   `-- exceptions.py
|       |
|       |-- orchestration/
|       |   |-- __init__.py
|       |   |-- coordinator.py
|       |   |-- router.py
|       |   `-- output_builder.py
|       |
|       |-- agents/
|       |   |-- __init__.py
|       |   |-- entity_agent.py
|       |   |-- order_product_agent.py
|       |   |-- shipment_agent.py
|       |   |-- payment_refund_agent.py
|       |   |-- policy_agent.py
|       |   |-- conflict_resolver.py
|       |   `-- verifier.py
|       |
|       |-- evidence/
|       |   |-- __init__.py
|       |   |-- evidence_store.py
|       |   |-- tool_cache.py
|       |   `-- tool_registry.py
|       |
|       `-- rules/
|           |-- __init__.py
|           |-- routing.py
|           |-- confidence.py
|           |-- source_precedence.py
|           `-- consistency.py
|
|-- tests/
|   |-- unit/
|   |   |-- test_entity_agent.py
|   |   |-- test_router.py
|   |   |-- test_shipment_agent.py
|   |   |-- test_payment_agent.py
|   |   |-- test_conflict_resolver.py
|   |   `-- test_verifier.py
|   |
|   |-- integration/
|   |   |-- test_workflow.py
|   |   `-- test_trace.py
|   |
|   |-- fixtures/
|   |   |-- sample_cases.py
|   |   `-- mock_evidence.py
|   |
|   |-- test_starter.py
|   `-- test_release_safety.py
|
|-- contracts/
|-- inputs/
|-- outputs/
|-- traces/
|-- ARCHITECTURE.md
|-- PROJECT_STRUCTURE.md
|-- README.md
|-- pyproject.toml
|-- .env.example
`-- .env
```

## 2. Vai trò của các thành phần

### `core/` - Cấu trúc dùng chung

- `context.py`: quản lý trạng thái xử lý riêng của từng case, cache, ngân sách gọi tool và evidence đã thu thập.
- `messages.py`: định nghĩa message envelope (vỏ thông điệp) dùng khi giao việc và handoff (bàn giao) giữa các agent.
- `agent_result.py`: định nghĩa kết quả chung mà mọi agent phải trả về.
- `exceptions.py`: định nghĩa lỗi nghiệp vụ, lỗi MCP và lỗi validation (xác thực).

Kết quả chung của agent chỉ có đúng năm field:

```python
{
    "status": "ok",
    "data": {},
    "evidence_refs": [],
    "confidence": 0.9,
    "issues": []
}
```

Giá trị `status` cho phép:

- `ok`: đã xử lý đầy đủ.
- `partial`: có kết quả nhưng còn thiếu dữ liệu.
- `error`: không thể xử lý.
- `skipped`: Router xác định không cần chạy.

`case_id`, `task_id`, source và target thuộc message envelope, không nằm trong kết quả agent.

### `orchestration/` - Điều phối

- `router.py`: đọc nội dung case và quyết định agent nào cần chạy.
- `coordinator.py`: giao nhiệm vụ, nhận handoff và kiểm soát toàn bộ vòng đời case.
- `output_builder.py`: tổng hợp kết quả các agent thành output đúng schema L3B.

`workflow.py` chỉ giữ entry point (điểm bắt đầu):

```python
async def solve_case(case, gateway, trace):
    coordinator = Coordinator(gateway, trace)
    return await coordinator.solve(case)
```

### `agents/` - Xử lý nghiệp vụ

- `entity_agent.py`: xác định order và customer từ exact ID hoặc candidate.
- `order_product_agent.py`: phân tích order, item, seller và product.
- `shipment_agent.py`: dựng timeline và xác định nguyên nhân giao hàng.
- `payment_refund_agent.py`: đối soát thanh toán, thu trùng và hoàn tiền.
- `policy_agent.py`: áp dụng chính sách để đề xuất hành động.
- `conflict_resolver.py`: xử lý xung đột giữa các nguồn dữ liệu.
- `verifier.py`: kiểm tra output, evidence và tính nhất quán trước khi hoàn tất.

Các agent không gọi trực tiếp lẫn nhau. Mọi phân công và handoff đều đi qua Coordinator.

### `evidence/` - Quản lý bằng chứng

- `evidence_store.py`: lưu evidence theo đúng `case_id` và ngăn dùng chéo case.
- `tool_cache.py`: cache kết quả theo `(case_id, tool_name, arguments)` để tránh gọi MCP trùng.
- `tool_registry.py`: lưu danh sách tool được discovery (khám phá) từ MCP server và ánh xạ tool với domain nghiệp vụ.

Không hard-code (ghi cứng) tên MCP tool trước khi lấy danh sách từ server.

### `rules/` - Quy tắc quyết định

- `routing.py`: quy tắc chọn agent theo loại claim.
- `confidence.py`: quy tắc tính và giảm confidence khi thiếu hoặc xung đột evidence.
- `source_precedence.py`: thứ tự ưu tiên nguồn khi dữ liệu mâu thuẫn.
- `consistency.py`: các kiểm tra chéo giữa entity, shipment, payment, refund và action.

Việc tách rules khỏi agent giúp dễ kiểm thử và điều chỉnh mà không sửa toàn bộ workflow.

## 3. Luồng phụ thuộc

```text
workflow.py
    |
    `-- Coordinator
        |-- Router
        |-- Agents
        |   `-- Evidence Store
        |       `-- MCP Gateway
        |-- Conflict Resolver
        |-- Output Builder
        `-- Verifier
```

Quy tắc phụ thuộc:

- `core` không phụ thuộc agent hoặc orchestration.
- `agents` được sử dụng `core`, `rules` và `evidence`.
- `orchestration` được sử dụng các agent.
- Agent không import `workflow.py`.
- Agent không gọi trực tiếp agent khác.
- `verifier.py` không tự thay đổi output; nó trả lỗi về Coordinator.
- Chỉ `mcp_gateway.py` giao tiếp trực tiếp với MCP server.

## 4. Luồng xử lý một case

```text
Input case
    |
    v
Entity Resolver
    |
    v
Router / Coordinator
    |
    |-- Order/Product Agent
    |-- Shipment Agent (khi liên quan vận chuyển)
    |-- Payment/Refund Agent (khi liên quan tài chính)
    `-- Policy Agent (khi cần quyết định chính sách)
            |
            v
     Conflict Resolver
            |
            v
      Output Builder
            |
            v
         Verifier
            |
       +----+----+
       |         |
     hợp lệ   chưa hợp lệ
       |         |
       v         `-- trả Coordinator sửa tối đa một lần
 Output JSON
 Trace JSONL
```

Entity Resolver phải chạy trước nếu order chưa được xác định chắc chắn. Router chỉ gọi các agent liên quan để giảm số MCP call (lượt gọi MCP).

## 5. Quy tắc định tuyến đề xuất

| Điều kiện | Agent được gọi |
| --- | --- |
| Chưa xác định chắc chắn order | Entity Resolver |
| Cần kiểm tra order, item, seller hoặc product | Order/Product Agent |
| Claim liên quan giao hàng | Shipment Agent |
| Claim liên quan thanh toán hoặc hoàn tiền | Payment/Refund Agent |
| Cần quyết định hành động hoặc quyền hoàn tiền | Policy Agent |
| Có dữ liệu từ hai nguồn không khớp | Conflict Resolver |
| Trước khi tạo output cuối | Verifier |

## 6. Trace bắt buộc

Một case hoàn chỉnh cần thể hiện được vòng đời sau:

```text
case_received
    -> task_assigned
    -> tool_result_consumed
    -> handoff
    -> policy_decided (nếu có)
    -> verification_completed
    -> case_finalized
```

Trace chỉ chứa các sự kiện có thể quan sát được, không chứa prompt hoặc chain-of-thought (chuỗi suy luận nội bộ).

## 7. Phân chia cho bốn thành viên

| Thành viên | Phạm vi chính | Đầu ra |
| --- | --- | --- |
| Designer (người thiết kế) | `core/`, `rules/`, `ARCHITECTURE.md` | Contract nội bộ, quy tắc và tài liệu kiến trúc |
| Router (người định tuyến) | `orchestration/`, `workflow.py` | Điều phối, handoff và tổng hợp output |
| Specialist (người làm nghiệp vụ) | `agents/`, `evidence/` | Các agent chuyên môn và quản lý evidence |
| Controller (người kiểm soát) | `verifier.py`, `tests/`, trace và submission | Kiểm tra chất lượng, test và đóng gói |

Người Specialist có khối lượng nghiệp vụ lớn nhất. Team có thể chuyển `entity_agent.py` cho Designer hoặc chuyển `conflict_resolver.py` cho Controller để cân bằng công việc.

## 8. Nguyên tắc triển khai

1. Mọi MCP call phải truyền đúng `case_id`.
2. Không tự tạo, sửa hoặc dùng chéo case một `evidence_ref`.
3. Cache chỉ tồn tại trong phạm vi case.
4. Retry phải có giới hạn và chỉ áp dụng cho lỗi tạm thời.
5. Không biến dữ liệu thiếu thành dữ liệu phỏng đoán.
6. Output phải được Verifier kiểm tra trước khi finalize.
7. Mỗi module nghiệp vụ phải có unit test (kiểm thử đơn vị).
8. Workflow hoàn chỉnh phải có integration test (kiểm thử tích hợp).
9. Không commit `.env`, input cuộc thi, output hoặc API key.

## 9. Nội dung cần team review

- Có giữ riêng `Conflict Resolver` hay đưa logic conflict vào Controller?
- Có chuyển `Entity Resolver` cho Designer để cân bằng khối lượng không?
- Ngân sách MCP call tối đa cho mỗi case là bao nhiêu?
- Cho phép sửa output sau verification tối đa bao nhiêu lần?
- Các agent chạy tuần tự hay song song sau khi đã resolve entity?
- Source precedence cụ thể giữa order, shipment, payment, refund và policy là gì?
