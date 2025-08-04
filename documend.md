# Tài liệu: Xử lý dữ liệu chấm công

## Mục đích
Mã nguồn này được thiết kế để xử lý dữ liệu chấm công từ một DataFrame đầu vào, xác định các ca làm việc (Ca sáng, Ca đêm, Thông ca, Sự kiện đặc biệt, hoặc Thiếu log), áp dụng các chính sách từ một DataFrame chính sách (nếu có), và tính toán các thông số như thời lượng ca, đi trễ, về sớm. Kết quả trả về là một DataFrame chứa thông tin chấm công đã được xử lý.

---

## Yêu cầu

### Thư viện
- Python 3.x
- pandas
- datetime
- re

### Dữ liệu đầu vào
1. **Dữ liệu chấm công (`df`)**:
   - Cột 0: `timestamp` (chuỗi thời gian, định dạng `YYYYMMDDHHMMSS`, ví dụ: `"20250804104700"`).
   - Cột 1: Không sử dụng.
   - Cột 2: `id` (ID nhân viên).
   - Cột 3: `first_name` (Tên).
   - Cột 4: `last_name` (Họ).
   - Cột 5: `key` (Loại log: "Vào" hoặc "Ra").

2. **Dữ liệu chính sách (`policy_df`)** (tùy chọn):
   - `ID`: ID nhân viên (chuỗi).
   - `start_day`: Thời gian bắt đầu ca sáng (định dạng `HH:MM:SS` hoặc `HH:MM`).
   - `start_night`: Thời gian bắt đầu ca đêm.
   - `end_day`: Thời gian kết thúc ca sáng.
   - `end_night`: Thời gian kết thúc ca đêm.
   - `late_tol`: Dung sai đi trễ (phút).
   - `early_tol`: Dung sai về sớm (phút).

---

## Các hàm chính

### 1. `parse_timestamp(ts)`
- **Mục đích**: Chuyển đổi chuỗi thời gian từ định dạng `YYYYMMDDHHMMSS` thành đối tượng `datetime`.
- **Tham số**:
  - `ts`: Chuỗi thời gian (str).
- **Trả về**: Đối tượng `datetime` nếu parse thành công, `None` nếu thất bại.
- **Lưu ý**: Chuỗi thời gian phải đúng định dạng, nếu không sẽ trả về `None`.

### 2. `natural_sort_key(val)`
- **Mục đích**: Tạo khóa sắp xếp tự nhiên cho chuỗi, hỗ trợ sắp xếp ID chứa cả chữ và số.
- **Tham số**:
  - `val`: Giá trị cần tạo khóa sắp xếp (thường là ID nhân viên).
- **Trả về**: Danh sách các phần tử (số hoặc chữ) để so sánh tự nhiên.
- **Ví dụ**: `ID123` sẽ được chia thành `["ID", 123]`.

### 3. `format_duration(hours)`
- **Mục đích**: Chuyển đổi thời lượng (giờ) thành chuỗi định dạng `"X giờ Y phút"`.
- **Tham số**:
  - `hours`: Thời lượng (giờ, dạng float).
- **Trả về**:
  - Chuỗi định dạng thời lượng (str), hoặc "" nếu `hours` là NaN, hoặc "0 phút" nếu thời lượng bằng 0.
- **Ví dụ**: `format_duration(2.5)` trả về `"2 giờ 30 phút"`.

### 4. `handle_single_logs(group, processed_indices, emp_id, name, records)`
- **Mục đích**: Xử lý các log đơn lẻ (chỉ có "Vào" hoặc "Ra") trong một nhóm dữ liệu của nhân viên.
- **Tham số**:
  - `group`: DataFrame chứa dữ liệu chấm công của một nhân viên.
  - `processed_indices`: Tập hợp các chỉ số đã xử lý để tránh lặp.
  - `emp_id`: ID nhân viên (str).
  - `name`: Tên đầy đủ của nhân viên (str).
  - `records`: Danh sách để lưu các bản ghi chấm công.
- **Hoạt động**:
  - Duyệt qua từng hàng trong `group`, bỏ qua các chỉ số đã xử lý.
  - Nếu log là "Vào":
    - Kiểm tra nếu giờ nằm trong khoảng 5h-10h hoặc trước 22h, gán loại ca là "Ca sáng thiếu log", nếu không thì "Thiếu LCO".
    - Tạo bản ghi với FCI (First Check-In) và LCO (Last Check-Out) là "Không có".
  - Nếu log là "Ra":
    - Gán loại ca là "Thiếu FCI".
    - Tạo bản ghi với LCO và FCI là "Không có".
  - Thêm bản ghi vào `records` với các thông tin như ID, Họ tên, Ngày, Thời lượng (h) (bằng 0), v.v.

### 5. `remove_nan_rows(df_result)`
- **Mục đích**: Loại bỏ các dòng trong DataFrame có giá trị NaN trong các cột quan trọng.
- **Tham số**:
  - `df_result`: DataFrame chứa dữ liệu chấm công đã xử lý.
- **Trả về**: DataFrame sau khi loại bỏ các dòng chứa NaN trong các cột: Thời lượng (h), Giờ vào, Giờ ra, FirstCheckIn, LastCheckOut.
- **Hoạt động**:
  - Đếm số dòng ban đầu.
  - Sử dụng `dropna` để loại bỏ các dòng có NaN trong các cột quan trọng.
  - In thông báo nếu có dòng bị loại bỏ.

### 6. `apply_policy_adjustments(df_result, policy_df)`
- **Mục đích**: Áp dụng chính sách từ `policy_df` để điều chỉnh dữ liệu chấm công, tính toán đi trễ/về sớm và thời lượng ca.
- **Tham số**:
  - `df_result`: DataFrame chứa dữ liệu chấm công đã xử lý.
  - `policy_df`: DataFrame chứa chính sách ca làm việc.
- **Trả về**: DataFrame đã được cập nhật với các cột Giờ vào, Giờ ra, Đi trễ/Về sớm, Thời lượng (h), và Ghi chú.
- **Hoạt động**:
  - Chuẩn hóa cột của `policy_df` và chuyển ID thành chuỗi.
  - Duyệt từng dòng trong `df_result`:
    - Nếu ID không có trong `policy_df`, ghi chú lỗi `POLICY_IS_NOT_EXIST`.
    - Chuyển đổi Ngày chấm công thành `pd.Timestamp`.
    - Bỏ qua nếu loại ca là "Thông ca".
    - Xác định `shift_start` và `shift_end` dựa trên loại ca (Ca sáng, Ca đêm, hoặc Ca sáng thiếu log).
    - Tính `duration_2` (thời lượng theo chính sách) và `duration_1` (thời lượng thực tế từ FirstCheckIn và LastCheckOut).
    - Tính đi trễ/về sớm với dung sai (`late_tol`, `early_tol`).
    - Chọn thời lượng nhỏ hơn giữa `duration_1` và `duration_2`, cập nhật cột Thời lượng (h) và Thời lượng.

### 7. `process_attendance(df, policy_df=None)`
- **Mục đích**: Hàm chính để xử lý dữ liệu chấm công, xác định loại ca, và áp dụng chính sách.
- **Tham số**:
  - `df`: DataFrame chứa dữ liệu chấm công thô.
  - `policy_df` (tùy chọn): DataFrame chứa chính sách ca làm việc.
- **Trả về**: DataFrame chứa dữ liệu chấm công đã xử lý với các cột:
  - ID, Họ tên, Ngày chấm công, Giờ vào, Giờ ra, FirstCheckIn, FCIStatus, LastCheckOut, LCOStatus, Thời lượng (h), Thời lượng, Loại ca, Log hôm trước, Ghi chú, Đi trễ/Về sớm (nếu có `policy_df`).
- **Hoạt động**:
  - Đổi tên cột của `df` và parse timestamp thành `datetime`.
  - Tạo cột `full_name` và sắp xếp theo id, datetime.
  - Nhóm dữ liệu theo id và `full_name`.
  - Duyệt từng nhóm:
    - Xử lý các log "Vào" và tìm log "Ra" tương ứng trong 30 giờ.
    - Xác định loại ca dựa trên giờ và thời lượng:
      - Thông ca: Nếu `fci.hour` >= 17 và thời lượng >= 17 giờ.
      - Ca sáng: Nếu `fci.hour` từ 4h-14h, `lco.hour` < 22, và thời lượng >= `TIME_FLAG` (4 giờ).
      - Ca đêm: Nếu `fci.hour` từ 16h-23h, `lco` sang ngày khác hoặc trước 10h, và thời lượng >= `TIME_FLAG`.
      - Sự kiện đặc biệt: Nếu thời lượng >= 15 giờ.
      - Thiếu log: Nếu chỉ có một log.
    - Ghi thông tin log của ngày trước nếu ca là "Thiếu log", "Ca sáng thiếu log", hoặc "Thiếu FCI".
    - Gọi `handle_single_logs` để xử lý các log đơn lẻ.
  - Tạo DataFrame từ `records`, sắp xếp theo ID, áp dụng chính sách (nếu có), và loại bỏ dòng chứa NaN.

---

## Debug và xử lý lỗi

### Nguyên nhân giá trị `NaN`
1. **Dữ liệu timestamp không hợp lệ**:
   - Chuỗi thời gian không đúng định dạng `YYYYMMDDHHMMSS`.
2. **Xử lý `fci` và `lco` không an toàn**:
   - Nếu `fci` hoặc `lco` là `NaN`, các phép tính thời lượng sẽ trả về `NaN`.
3. **Dữ liệu chính sách không hợp lệ**:
   - Thời gian trong `policy_df` không đúng định dạng (ví dụ: `"25:00:00"`).

### Giải pháp
1. Kiểm tra và làm sạch dữ liệu đầu vào (`df` và `policy_df`) trước khi xử lý.
2. Sử dụng `errors='coerce'` trong `pd.to_datetime` để xử lý các giá trị thời gian không hợp lệ.
3. Thêm debug để ghi lại các giá trị timestamp hoặc thời gian trong `policy_df` gây lỗi.

### Debug
- Kiểm tra `NaN` trong `df` sau khi parse:
  ```python
  print(df[df['datetime'].isna()])
  ```
- Kiểm tra `policy_df`:
  ```python
  print(policy_df[['start_day', 'start_night', 'end_day', 'end_night']].isna().sum())
  ```

---

## Kết quả đầu ra

DataFrame với các cột:
- `ID`: ID nhân viên.
- `Họ tên`: Tên đầy đủ.
- `Ngày chấm công`: Ngày chấm công (định dạng `DD-MM-YYYY`).
- `Giờ vào`, `Giờ ra`: Thời gian vào/ra theo chính sách hoặc thực tế.
- `FirstCheckIn`, `LastCheckOut`: Thời gian check-in/check-out thực tế.
- `FCIStatus`, `LCOStatus`: Trạng thái ("Vào", "Ra", hoặc "Không có").
- `Thời lượng (h)`: Thời lượng ca (giờ, làm tròn 2 chữ số).
- `Thời lượng`: Chuỗi thời lượng (e.g., `"8 giờ 30 phút"`).
- `Loại ca`: Loại ca làm việc.
- `Log hôm trước`: Thông tin log của ngày trước (nếu có).
- `Ghi chú`: Ghi chú về lỗi hoặc trạng thái.
- `Đi trễ/Về sớm`: Trạng thái đi trễ/về sớm (nếu có `policy_df`).

---

## Ví dụ sử dụng
```python
import pandas as pd

# Dữ liệu chấm công
data = {
    0: ["20250804104700", "20250804180000"],
    1: ["", ""],
    2: ["123", "123"],
    3: ["John", "John"],
    4: ["Doe", "Doe"],
    5: ["Vào", "Ra"]
}
df = pd.DataFrame(data)

# Dữ liệu chính sách
policy_data = {
    'ID': ['123'],
    'start_day': ['08:00:00'],
    'start_night': ['20:00:00'],
    'end_day': ['17:00:00'],
    'end_night': ['05:00:00'],
    'late_tol': [5],
    'early_tol': [5]
}
policy_df = pd.DataFrame(policy_data)

# Xử lý chấm công
result = process_attendance(df, policy_df)
print(result)
```
