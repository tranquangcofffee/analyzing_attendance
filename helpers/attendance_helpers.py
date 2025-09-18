from datetime import datetime, timedelta
import pandas as pd
import re
from math import floor

def extract_time_only(x):
    try:
        dt = pd.to_datetime(x, format='%d/%m - %H:%M:%S', errors='coerce')
        return dt.strftime('%H:%M:%S') if not pd.isna(dt) else 'Không có'
    except:
        return 'Không có'

def parse_timestamp(ts):
    try:
        return datetime.strptime(str(ts), "%Y%m%d%H%M%S")
    except:
        return None

def natural_sort_key(val):
    parts = re.split(r'(\d+)', str(val))
    return [int(part) if part.isdigit() else part.lower() for part in parts]

def format_duration(hours):
    if pd.isna(hours):
        return ""
    total_minutes = int(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h} giờ {m} phút" if total_minutes > 0 else "0 phút"

def handle_single_logs(group, processed_indices, emp_id, name, records):
    for idx, row in group.iterrows():
        if idx in processed_indices:
            continue

        log_date = row['datetime'].date()
        fci = row['datetime']
        
        # Kiểm tra ca sáng thiếu log
        log_count = 1  # Giả sử chỉ có 1 log (Vào hoặc Ra)
        shift_type = None
        if row['key'] == 'Vào':
            if 5 <= fci.hour <= 10 or fci.hour < 22:
                shift_type = 'Ca sáng thiếu log'
            else:
                shift_type = 'Thiếu LCO'
                
            records.append({
                'ID': emp_id,
                'Họ tên': name,
                'Ngày': log_date,
                'FCI': fci.strftime('%d/%m - %H:%M:%S'),
                'FCI trạng thái': 'Vào',
                'LCO': 'Không có',
                'LCO trạng thái': 'Không có',
                'Thời lượng (h)': 0,
                'Loại ca': shift_type,
                'Log hôm trước': 'None'
            })

        elif row['key'] == 'Ra':
            shift_type = 'Thiếu FCI'
            records.append({
                'ID': emp_id,
                'Họ tên': name,
                'Ngày': log_date,
                'FCI': 'Không có',
                'FCI trạng thái': 'Không có',
                'LCO': row['datetime'].strftime('%d/%m - %H:%M:%S'),
                'LCO trạng thái': 'Ra',
                'Thời lượng (h)': 0,
                'Loại ca': shift_type,
                'Log hôm trước': 'None'
            })

def replace_key_values(df):
    """Thay thế giá trị key: IN, IN DUTY -> Vào; OUT, OUT DUTY -> Ra."""
    key_mapping = {
        'IN': 'Vào',
        'IN DUTY': 'Vào',
        'OUT': 'Ra',
        'OUT DUTY': 'Ra'
    }
    df['key'] = df['key'].map(key_mapping).fillna(df['key'])
    return df

def remove_nan_rows(df_result):
    """Loại bỏ các dòng có giá trị NaN trong các cột quan trọng."""
    important_columns = ['Thời lượng (h)', 'Giờ vào', 'Giờ ra', 'FirstCheckIn', 'LastCheckOut']
    initial_rows = len(df_result)
    df_result = df_result.dropna(subset=important_columns, how='any')
    removed_rows = initial_rows - len(df_result)
    if removed_rows > 0:
        print(f"Đã loại bỏ {removed_rows} dòng chứa NaN trong các cột: {important_columns}")
    return df_result