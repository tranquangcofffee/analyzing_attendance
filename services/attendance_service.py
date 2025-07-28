from datetime import datetime, timedelta
import pandas as pd
import re

TIME_FLAG = 4

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

def check_morning_shift_with_missing_log(fci, log_count):
    if log_count <= 1:
        if 5 <= fci.hour <= 10 or fci.hour < 22:
            return 'Ca sáng thiếu log'
    return None

def handle_single_logs(group, processed_indices, emp_id, name, records):
    for idx, row in group.iterrows():
        if idx in processed_indices:
            continue

        log_date = row['datetime'].date()
        if row['key'] == 'Vào':
            records.append({
                'ID': emp_id,
                'Họ tên': name,
                'Ngày': log_date,
                'FCI': row['datetime'].strftime('%d/%m - %H:%M:%S'),
                'FCI trạng thái': 'Vào',
                'LCO': 'Không có',
                'LCO trạng thái': 'Không có',
                'Thời lượng (h)': 0,
                'Loại ca': 'Thiếu LCO',
                'Log hôm trước': 'None'
            })

        elif row['key'] == 'Ra':
            records.append({
                'ID': emp_id,
                'Họ tên': name,
                'Ngày': log_date,
                'FCI': 'Không có',
                'FCI trạng thái': 'Không có',
                'LCO': row['datetime'].strftime('%d/%m - %H:%M:%S'),
                'LCO trạng thái': 'Ra',
                'Thời lượng (h)': 0,
                'Loại ca': 'Thiếu FCI',
                'Log hôm trước': 'None'
            })

def apply_policy_adjustments(df_result, policy_df):
    """Áp dụng điều chỉnh chính sách từ file chính sách."""
    # Đảm bảo tên cột đúng
    expected_columns = ['ID', 'start_day', 'start_night', 'end_day', 'end_night', 'late_tol', 'early_tol']
    if not all(col in policy_df.columns for col in expected_columns):
        policy_df.columns = expected_columns[:len(policy_df.columns)]
    
    # Chuyển ID thành chuỗi và loại bỏ trùng lặp
    policy_df['ID'] = policy_df['ID'].astype(str)
    df_result['ID'] = df_result['ID'].astype(str)
    policy_df = policy_df.drop_duplicates(subset='ID')
    policy_map = policy_df.set_index('ID').to_dict('index')

    def parse_shift_time(date_ref, time_str):
        """Chuyển đổi chuỗi thời gian và kết hợp với ngày tham chiếu."""
        if pd.isna(time_str) or not isinstance(time_str, str):
            return None
        try:
            time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
            return datetime.combine(date_ref, time_obj)
        except ValueError:
            try:
                time_obj = datetime.strptime(time_str, "%H:%M").time()
                return datetime.combine(date_ref, time_obj)
            except:
                return None

    for idx, row in df_result.iterrows():
        emp_id = str(row['ID'])
        if emp_id not in policy_map:
            df_result.at[idx, 'Ghi chú'] = f"Không tìm thấy chính sách cho ID {emp_id}"
            continue

        policy = policy_map[emp_id]
        shift_type = row.get('Loại ca', '')
        date_ref = row.get('Ngày')

        # Kiểm tra và chuyển đổi date_ref
        try:
            if isinstance(date_ref, (datetime, pd.Timestamp)):
                date_ref = pd.Timestamp(date_ref)
            elif isinstance(date_ref, str):
                date_ref = pd.Timestamp(date_ref)
            elif isinstance(date_ref, pd.Timestamp.date):
                date_ref = pd.Timestamp(date_ref)
            else:
                df_result.at[idx, 'Ghi chú'] = f"Ngày tham chiếu không hợp lệ: {type(date_ref)}"
                continue
        except Exception as e:
            df_result.at[idx, 'Ghi chú'] = f"Lỗi chuyển đổi ngày: {str(e)}"
            continue

        # Bỏ qua nếu là Thông ca
        if 'Thông ca' in shift_type:
            df_result.at[idx, 'Ghi chú'] = "Bỏ qua vì là Thông ca"
            continue

        # Xác định thời gian bắt đầu và kết thúc dựa trên loại ca
        if 'Ca đêm' in shift_type:
            shift_start = parse_shift_time(date_ref, policy.get('start_night'))
            shift_end = parse_shift_time(date_ref, policy.get('end_night'))
            if shift_end and shift_start and shift_end < shift_start:
                shift_end += timedelta(days=1)
        elif 'Ca sáng' in shift_type or 'Ca sáng thiếu log' in shift_type:
            shift_start = parse_shift_time(date_ref, policy.get('start_day'))
            shift_end = parse_shift_time(date_ref, policy.get('end_day'))
        else:
            df_result.at[idx, 'Ghi chú'] = f"Loại ca không được nhận diện: {shift_type}"
            continue

        if not shift_start or not shift_end:
            df_result.at[idx, 'Ghi chú'] = f"Thời gian chính sách không hợp lệ cho ID {emp_id}: start={policy.get('start_day')}, end={policy.get('end_day')}"
            continue

        # Ghi đè FCI/LCO và fci/lco với thời gian từ chính sách
        df_result.at[idx, 'fci'] = shift_start
        df_result.at[idx, 'lco'] = shift_end
        df_result.at[idx, 'FCI'] = shift_start.strftime('%d/%m - %H:%M:%S')
        df_result.at[idx, 'LCO'] = shift_end.strftime('%d/%m - %H:%M:%S')

        # Tính toán và ghi đè thời lượng ca
        shift_duration = (shift_end - shift_start).total_seconds() / 3600
        df_result.at[idx, 'Thời lượng (h)'] = round(shift_duration, 2)
        df_result.at[idx, 'Thời lượng'] = format_duration(shift_duration)
        df_result.at[idx, 'Ghi chú'] = "Đã áp dụng thời gian chính sách"

    return df_result

def process_attendance(df, policy_df=None):
    """Xử lý dữ liệu chấm công và áp dụng điều chỉnh chính sách."""
    # Đổi tên cột cho phù hợp
    df = df.rename(columns={
        df.columns[0]: "timestamp",
        df.columns[1]: "unused",
        df.columns[2]: "id",
        df.columns[3]: "first_name",
        df.columns[4]: "last_name",
        df.columns[5]: "key"
    })

    # Phân tích timestamp và loại bỏ hàng không hợp lệ
    df['datetime'] = df['timestamp'].apply(parse_timestamp)
    df.dropna(subset=['datetime'], inplace=True)
    
    # Tạo tên đầy đủ và sắp xếp theo ID, thời gian
    df['full_name'] = df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)
    df = df.sort_values(by=['id', 'datetime'])

    records = []
    grouped = df.groupby(['id', 'full_name'])

    TIME_FLAG = 4  # Số giờ tối thiểu cho ca hợp lệ

    for (emp_id, name), group in grouped:
        group = group.sort_values(by='datetime').reset_index(drop=True)
        group['date'] = group['datetime'].dt.date
        group_by_date = group.groupby('date')

        processed_indices = set()
        i = 0

        while i < len(group):
            row = group.iloc[i]
            if row['key'] != 'Vào':
                i += 1
                continue

            fci = row['datetime']
            fci_status = row['key']
            shift_type = "Không hợp lệ"
            lco = fci
            lco_status = "Không có"
            log_count = 1
            found_lco = False

            processed_indices.add(i)

            j = i + 1
            while j < len(group):
                next_row = group.iloc[j]
                time_diff = (next_row['datetime'] - fci).total_seconds() / 3600

                if next_row['key'] == 'Ra' and time_diff <= 30:
                    lco = next_row['datetime']
                    lco_status = next_row['key']
                    log_count += 1
                    found_lco = True
                    processed_indices.add(j)
                    break
                j += 1

            duration = (lco - fci).total_seconds() / 3600
            date_report = fci.date()

            if log_count <= 1:
                morning_shift = check_morning_shift_with_missing_log(fci, log_count)
                shift_type = morning_shift if morning_shift else 'Thiếu log'
            else:
                if duration >= 17:
                    shift_type = 'Thông ca'
                elif 5 <= fci.hour <= 10 and lco.hour < 20 and duration >= TIME_FLAG:
                    shift_type = 'Ca sáng'
                elif 16 <= fci.hour <= 23 and duration >= TIME_FLAG:
                    if lco.date() > fci.date() or lco.hour <= 8:
                        shift_type = 'Ca đêm'

            prev_day = date_report - timedelta(days=1)
            prev_log_info = "Không có"

            if shift_type in ['Thiếu log', 'Ca sáng thiếu log']:
                if prev_day in group_by_date.groups:
                    prev_logs = group_by_date.get_group(prev_day)
                    prev_entries = [
                        f"{r['key']} @ {r['datetime'].strftime('%H:%M:%S')}"
                        for _, r in prev_logs.iterrows()
                    ]
                    prev_log_info = "; ".join(prev_entries)

            records.append({
                'ID': str(emp_id),  # Đảm bảo ID là chuỗi
                'Họ tên': name,
                'Ngày': pd.Timestamp(date_report),  # Chuyển thành pd.Timestamp
                'FCI': fci.strftime('%d/%m - %H:%M:%S'),
                'FCI trạng thái': fci_status,
                'LCO': lco.strftime('%d/%m - %H:%M:%S'),
                'LCO trạng thái': lco_status,
                'fci': fci,
                'lco': lco,
                'Thời lượng (h)': round(duration, 2),
                'Thời lượng': format_duration(duration),
                'Loại ca': shift_type,
                'Log hôm trước': prev_log_info
            })

            i = j if found_lco else i + 1

        handle_single_logs(group, processed_indices, emp_id, name, records)

    df_result = pd.DataFrame(records)
    df_result['Ghi chú'] = ""
    df_result.sort_values(by='ID', key=lambda x: x.map(natural_sort_key), inplace=True)

    # Áp dụng điều chỉnh chính sách nếu có policy_df
    if policy_df is not None:
        df_result = apply_policy_adjustments(df_result, policy_df)

    return df_result