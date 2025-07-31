from datetime import datetime, timedelta
import pandas as pd
import re

#region # Constants and error messages
TIME_FLAG = 4
DAY_PARSE_ERROR = 'Ngày không hợp lệ, vui lòng kiểm tra định dạng ngày tháng năm.'
MISSING_CHECKIN = 'Thiếu check-in, vui lòng kiểm tra dữ liệu chấm công.'
MISSING_CHECKOUT = 'Thiếu check-out, vui lòng kiểm tra dữ liệu chấm công.'
MISSING_SCAN_BIO = 'Thiếu dữ liệu xử lý (FCI/LCO) {0}, vui lòng kiểm tra dữ liệu chấm công.'
THROUGH_SHIFT = 'Thông ca'
THROUGH_SHIFT_PASSED = 'Bỏ qua vì là Thông ca'
POLICY_IS_NOT_APPLICABLE = 'Chính sách không áp dụng cho nhân sự này'
POLICY_IS_NOT_EXIST = 'Chính sách không tồn tại cho nhân sự {0}'
#endregion

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
    """Áp dụng điều chỉnh chính sách từ file chính sách, lưu Giờ vào/ra theo chính sách, tính đi trễ/về sớm."""
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
        if pd.isna(time_str) or not isinstance(time_str, str) or time_str.strip() == '':
            return None
        try:
            time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
            return datetime.combine(date_ref.date(), time_obj)
        except ValueError:
            try:
                time_obj = datetime.strptime(time_str, "%H:%M").time()
                return datetime.combine(date_ref.date(), time_obj)
            except:
                return None

    # Thêm cột mới cho đi trễ/về sớm
    df_result['Đi trễ/Về sớm'] = ""

    for idx, row in df_result.iterrows():
        emp_id = str(row['ID'])
        if emp_id not in policy_map:
            df_result.at[idx, 'Ghi chú'] = POLICY_IS_NOT_EXIST.format(emp_id)
            df_result.at[idx, 'Đi trễ/Về sớm'] = POLICY_IS_NOT_EXIST
            continue

        policy = policy_map[emp_id]
        shift_type = row.get('Loại ca', '')
        date_ref = row.get('Ngày chấm công')

        # Kiểm tra và chuyển đổi date_ref
        try:
            if isinstance(date_ref, (datetime, pd.Timestamp)):
                date_ref = pd.Timestamp(date_ref)
            elif isinstance(date_ref, str):
                date_ref = pd.Timestamp(date_ref)
            elif isinstance(date_ref, pd.Timestamp.date):
                date_ref = pd.Timestamp(date_ref)
            else:
                df_result.at[idx, 'Ghi chú'] = DAY_PARSE_ERROR
                df_result.at[idx, 'Đi trễ/Về sớm'] = DAY_PARSE_ERROR
                continue
        except Exception as e:
            df_result.at[idx, 'Ghi chú'] = MISSING_SCAN_BIO
            df_result.at[idx, 'Đi trễ/Về sớm'] = DAY_PARSE_ERROR
            continue

        # Bỏ qua nếu là Thông ca
        if 'Thông ca' in shift_type:
            df_result.at[idx, 'Ghi chú'] = THROUGH_SHIFT_PASSED
            df_result.at[idx, 'Đi trễ/Về sớm'] = THROUGH_SHIFT
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
            df_result.at[idx, 'Đi trễ/Về sớm'] = "Loại ca không xác định"
            continue

        if not shift_start or not shift_end:
            df_result.at[idx, 'Ghi chú'] = POLICY_IS_NOT_APPLICABLE
            df_result.at[idx, 'Đi trễ/Về sớm'] = "Thời gian chính sách không hợp lệ"
            continue

        # Gán Giờ vào và Giờ ra theo chính sách
        df_result.at[idx, 'Giờ vào'] = shift_start.strftime('%d/%m - %H:%M:%S') if shift_start else "Không có"
        df_result.at[idx, 'Giờ ra'] = shift_end.strftime('%d/%m - %H:%M:%S') if shift_end else "Không có"

        # Tính duration_2 từ chính sách
        duration_2 = (shift_end - shift_start).total_seconds() / 3600 if shift_start and shift_end else 0

        # Lấy duration_1 từ LastCheckOut - FirstCheckIn (nếu có)
        fci_str = row.get('FirstCheckIn')
        lco_str = row.get('LastCheckOut')
        duration_1 = row.get('Thời lượng (h)', 0)
        if fci_str != 'Không có' and lco_str != 'Không có':
            try:
                fci = pd.to_datetime(fci_str, format='%d/%m - %H:%M:%S')
                lco = pd.to_datetime(lco_str, format='%d/%m - %H:%M:%S')
                duration_1 = (lco - fci).total_seconds() / 3600
            except Exception as e:
                duration_1 = 0
                df_result.at[idx, 'Ghi chú'] = f"Lỗi parse FirstCheckIn/LastCheckOut: {str(e)}"
        else:
            fci = None
            lco = None
            df_result.at[idx, 'Ghi chú'] = "Thiếu check-in/check-out, dùng thời gian chính sách"

        # Tính đi trễ và về sớm với dung sai
        late_minutes = 0
        early_minutes = 0
        late_tolerance = float(policy.get('late_tol', 0)) if not pd.isna(policy.get('late_tol')) else 0
        early_tolerance = float(policy.get('early_tol', 0)) if not pd.isna(policy.get('early_tol')) else 0
        status = []

        if fci_str != 'Không có' and lco_str != 'Không có':
            # Đảm bảo fci và lco cùng ngày với shift_start và shift_end
            if fci.date() != shift_start.date():
                fci = datetime.combine(shift_start.date(), fci.time())
            if lco.date() != shift_end.date():
                lco = datetime.combine(shift_end.date(), lco.time())

            # Tính đi trễ với dung sai
            shift_start_with_tol = shift_start + timedelta(minutes=late_tolerance)
            if fci > shift_start_with_tol:
                late_minutes = (fci - shift_start_with_tol).total_seconds() / 60
                if late_minutes > 0:
                    status.append(f"Đi trễ {int(late_minutes)} phút")

            # Tính về sớm với dung sai
            shift_end_with_tol = shift_end - timedelta(minutes=early_tolerance)
            if lco < shift_end_with_tol:
                early_minutes = (shift_end_with_tol - lco).total_seconds() / 60
                if early_minutes > 0 and early_minutes < 1440:
                    status.append(f"Về sớm {int(early_minutes)} phút")

        # Ghi trạng thái đi trễ/về sớm
        df_result.at[idx, 'Đi trễ/Về sớm'] = ", ".join(status) if status else "Đúng giờ"

        # Chọn thời lượng hợp lý
        if duration_1 > duration_2:
            final_duration = duration_2
            df_result.at[idx, 'Ghi chú'] = "Dùng thời lượng chính sách (Giờ ra - Giờ vào)" if duration_2 > 0 else df_result.at[idx, 'Ghi chú']
        else:
            final_duration = duration_1
            df_result.at[idx, 'Ghi chú'] = "Dùng thời lượng thực tế (LastCheckOut - FirstCheckIn)" if duration_1 > 0 else df_result.at[idx, 'Ghi chú']

        df_result.at[idx, 'Thời lượng (h)'] = round(final_duration, 2)
        df_result.at[idx, 'Thời lượng'] = format_duration(final_duration)

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

    TIME_FLAG = 6  # Số giờ tối thiểu cho ca hợp lệ

    for (emp_id, name), group in grouped:
        group = group.sort_values(by='datetime').reset_index()
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
                # if duration >= 17:
                #     shift_type = 'Thông ca'
                # elif 5 <= fci.hour <= 10 and lco.hour < 20 and duration >= TIME_FLAG:
                #     shift_type = 'Ca sáng'
                # elif 16 <= fci.hour <= 23 and duration >= TIME_FLAG:
                #     if lco.date() > fci.date() or lco.hour <= 8:
                #         shift_type = 'Ca đêm'

                if 17 <= fci.hour and duration >= 17:
                    shift_type = 'Thông ca'

                # Nới rộng giờ ra để quét
                elif 4 <= fci.hour <= 14 and lco.hour < 22 and duration >= TIME_FLAG:
                    # Ca sáng — kiểm tra xem có nhiều log trong ngày không
                    same_day_logs = group[group['date'] == fci.date()]
                    morning_fc_in = same_day_logs[same_day_logs['key'] == 'Vào']
                    morning_lc_out = same_day_logs[same_day_logs['key'] == 'Ra']
                    
                    if len(morning_fc_in) > 1 or len(morning_lc_out) > 1:
                        # Lấy FCI sớm nhất, LCO trễ nhất trong ngày
                        earliest_fci = morning_fc_in['datetime'].min()
                        latest_lco = morning_lc_out[morning_lc_out['datetime'].dt.hour < 22]['datetime'].max()
                        new_duration = (latest_lco - earliest_fci).total_seconds() / 3600 if pd.notna(latest_lco) else 0
                        
                        if new_duration >= TIME_FLAG:
                            fci = earliest_fci
                            lco = latest_lco
                            duration = new_duration
                            shift_type = 'Ca sáng'
                    else:
                        shift_type = 'Ca sáng'

                elif 16 <= fci.hour <= 23 and duration >= TIME_FLAG:
                    if lco.date() > fci.date() or lco.hour <= 10:
                        shift_type = 'Ca đêm'

            prev_day = date_report - timedelta(days=1)
            prev_log_info = "Không có"

            if shift_type in ['Thiếu log', 'Ca sáng thiếu log', 'Thiếu FCI']:
                if prev_day in group_by_date.groups:
                    prev_logs = group_by_date.get_group(prev_day)
                    prev_entries = [
                        f"{r['key']} @ {r['datetime'].strftime('%H:%M:%S')}"
                        for _, r in prev_logs.iterrows()
                    ]
                    prev_log_info = "; ".join(prev_entries)

            records.append({
                'ID': str(emp_id),
                'Họ tên': name,
                'Ngày chấm công': date_report.strftime('%d-%m-%Y'),
                'FirstCheckIn': fci.strftime('%d/%m - %H:%M:%S'),
                'FCIStatus': fci_status,
                'LastCheckOut': lco.strftime('%d/%m - %H:%M:%S'),
                'LCOStatus': lco_status,
                'Giờ vào': fci.strftime('%d/%m - %H:%M:%S'),
                'Giờ ra': lco.strftime('%d/%m - %H:%M:%S'),
                'Thời lượng (h)': round(duration, 2),
                'Thời lượng': format_duration(duration),
                'Loại ca': shift_type,
                'Log hôm trước': prev_log_info
            })

            i = j if found_lco else i + 1

        handle_single_logs(group, processed_indices, emp_id, name, records)

    df_result = pd.DataFrame(records)
    df_result['Ghi chú'] = ""
    df_result = df_result[[
        'ID', 'Họ tên', 'Ngày chấm công', 'Giờ vào', 'Giờ ra', 'FirstCheckIn', 'FCIStatus',
        'LastCheckOut', 'LCOStatus', 'Thời lượng (h)', 'Thời lượng', 'Loại ca',
        'Log hôm trước', 'Ghi chú'
    ]]
    df_result.sort_values(by='ID', key=lambda x: x.map(natural_sort_key), inplace=True)

    # Áp dụng điều chỉnh chính sách nếu có policy_df
    if policy_df is not None:
        df_result = apply_policy_adjustments(df_result, policy_df)

    return df_result