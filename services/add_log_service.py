import pandas as pd
from datetime import datetime
from services.attendance_service import process_attendance

def reconstruct_raw_data_from_attendance(attendance_data):
    if attendance_data is None:
        print("Error: attendance_data is None")
        return None
    
    df = pd.DataFrame(attendance_data)
    if df.empty:
        print("Error: attendance_data is empty")
        return None
    
    raw_data = []
    id_column = None
    possible_id_columns = ['ID', 'id', 'Mã nhân viên', 'MaNV', 'EmployeeID', 'employee_id', 'msnv']
    for col in possible_id_columns:
        if col in df.columns:
            id_column = col
            break
    if id_column is None:
        print(f"Error: No ID column found in attendance_data (columns: {df.columns.tolist()})")
        return None
    
    for _, row in df.iterrows():
        id_emp = row[id_column]
        full_name = row.get('Họ tên', '').split() if 'Họ tên' in df.columns else ['']
        first_name = full_name[0] if full_name else ''
        last_name = ' '.join(full_name[1:]) if len(full_name) > 1 else ''
        date_str = row.get('Ngày chấm công', None)
        
        if date_str and pd.notna(row.get('FirstCheckIn', None)):
            try:
                dt_in = pd.to_datetime(f"{date_str} {row['FirstCheckIn']}", format='%d/%m/%Y %H:%M')
                timestamp_in = int(dt_in.strftime('%Y%m%d%H%M%S'))
                raw_data.append({
                    'timestamp': timestamp_in,
                    'id': id_emp,
                    'first_name': first_name,
                    'last_name': last_name,
                    'key': 'Vào',
                    'unused': 0
                })
            except ValueError as e:
                print(f"Error parsing Giờ vào for ID {id_emp}: {e}")
        
        if date_str and pd.notna(row.get('LastCheckOut', None)):
            try:
                dt_out = pd.to_datetime(f"{date_str} {row['LastCheckOut']}", format='%d/%m/%Y %H:%M')
                timestamp_out = int(dt_out.strftime('%Y%m%d%H%M%S'))
                raw_data.append({
                    'timestamp': timestamp_out,
                    'id': id_emp,
                    'first_name': first_name,
                    'last_name': last_name,
                    'key': 'Ra',
                    'unused': 0
                })
            except ValueError as e:
                print(f"Error parsing Giờ ra for ID {id_emp}: {e}")
    
    if not raw_data:
        print("Error: Reconstructed raw_data is empty")
    return raw_data if raw_data else None

def add_log_service(raw_data, policy_data, id_emp, datetime_str, key):
    """
    Thêm log bù vào dữ liệu chấm công và re-process.
    
    Args:
        raw_data (list): Dữ liệu chấm công gốc (danh sách các dictionary).
        policy_data (list or None): Dữ liệu chính sách (dict từ DataFrame hoặc None).
        id_emp (str): ID nhân viên.
        datetime_str (str): Chuỗi thời gian (YYYY-MM-DDTHH:MM hoặc YYYY-MM-DD HH:MM).
        key (str): Loại log ('Vào' hoặc 'Ra').
    
    Returns:
        tuple: (raw_df, result_df, error) - raw_df và result_df là DataFrame hoặc None, error là str hoặc None.
    """
    try:
        if not raw_data:
            print("raw_data is empty or None")
            return None, None, "Dữ liệu chấm công gốc rỗng."
        
        # Kiểm tra xem raw_data có phải danh sách các dictionary không
        if not isinstance(raw_data, list) or not all(isinstance(item, dict) for item in raw_data):
            print("Error: raw_data is not a list of dictionaries")
            return None, None, "Dữ liệu chấm công gốc không đúng định dạng (phải là danh sách các dictionary)."

        # Tạo DataFrame từ raw_data
        raw_df = pd.DataFrame(raw_data)
        print(f"raw_data columns: {raw_df.columns.tolist()}")
        print(f"raw_data size: {len(raw_df)} records")
        if not raw_df.empty:
            print("raw_data sample (first 2 rows):")
            print(raw_df.head(2).to_dict(orient='records'))

        # Ánh xạ cột không chuẩn sang cột chuẩn
        # Dựa trên dòng mẫu, giả định cấu trúc cột như sau:
        # ['20250814101634', 'Unnamed: 1', '172', 'Vay', 'Thanh Tân', 'Ra'] -> ['timestamp', 'unused', 'id', 'first_name', 'last_name', 'key']
        column_mapping = {
            raw_df.columns[0]: 'timestamp',  # Cột đầu tiên là timestamp
            raw_df.columns[1]: 'unused',     # Cột thứ hai là unused
            raw_df.columns[2]: 'id',        # Cột thứ ba là id
            raw_df.columns[3]: 'first_name',# Cột thứ tư là first_name
            raw_df.columns[4]: 'last_name', # Cột thứ năm là last_name
            raw_df.columns[5]: 'key'        # Cột thứ sáu là key
        }

        # Kiểm tra số cột
        if len(raw_df.columns) != 6:
            print(f"Error: raw_data has {len(raw_df.columns)} columns, expected 6.")
            return None, None, f"Dữ liệu chấm công gốc có {len(raw_df.columns)} cột, cần đúng 6 cột."

        # Đổi tên cột
        raw_df = raw_df.rename(columns=column_mapping)
        print(f"Renamed raw_data columns: {raw_df.columns.tolist()}")

        # Đảm bảo cột 'unused' có giá trị mặc định
        raw_df['unused'] = raw_df['unused'].fillna(0)

        # Kiểm tra ID nhân viên
        matching = raw_df[raw_df['id'].astype(str) == str(id_emp)]
        if matching.empty:
            print(f"No matching ID {id_emp} found in raw_data")
            return None, None, f"ID {id_emp} không tồn tại trong dữ liệu."

        first_name = matching['first_name'].iloc[0]
        last_name = matching['last_name'].iloc[0]

        # Tạo log mới
        try:
            dt = pd.to_datetime(datetime_str, format='%Y-%m-%d %H:%M')
            timestamp = int(dt.strftime('%Y%m%d%H%M%S'))
        except ValueError:
            try:
                dt = pd.to_datetime(datetime_str, format='%Y-%m-%dT%H:%M')
                timestamp = int(dt.strftime('%Y%m%d%H%M%S'))
            except ValueError:
                print(f"Invalid datetime format: {datetime_str}")
                return None, None, "Định dạng giờ bù không hợp lệ (dùng YYYY-MM-DD HH:MM hoặc YYYY-MM-DDTHH:MM)."

        new_log = {
            'timestamp': timestamp,
            'id': str(id_emp),
            'first_name': first_name,
            'last_name': last_name,
            'key': key,
            'unused': 0
        }
        print(f"Adding new log: {new_log}")

        # Thêm log mới vào DataFrame
        raw_df = pd.concat([raw_df, pd.DataFrame([new_log])], ignore_index=True)

        # Gọi hàm process_attendance
        result_df = process_attendance(raw_df, policy_data)

        return raw_df, result_df, None

    except Exception as e:
        print(f"Error in add_log_service: {str(e)}")
        return None, None, f"Lỗi khi thêm log: {str(e)}"