import os
from flask import Flask, request, render_template, redirect, url_for, send_file
from flask_caching import Cache
from datetime import datetime
import pandas as pd
from services.attendance_service import process_attendance, format_duration
from services.excel_service import save_excel, get_excel_path
from io import BytesIO

app = Flask(__name__)
df_result = pd.DataFrame()

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 60 * 60  # giữ cache 1 giờ
cache = Cache(app)

def sort_attendance_df(df):
    df_regular = df[~df['ID'].astype(str).str.startswith('OUTSIDE_')].copy()
    df_outside = df[df['ID'].astype(str).str.startswith('OUTSIDE_')].copy()

    # Sắp theo ID số (đối với nhân viên thường)
    df_regular['ID_sort'] = df_regular['ID'].astype(int)

    # Sắp theo số sau OUTSIDE_ (ví dụ OUTSIDE_3 -> 3)
    df_outside['ID_sort'] = df_outside['ID'].astype(str).str.extract(r'OUTSIDE_(\d+)').astype(int)

    # Sắp theo ID_sort và Ngày chấm công
    df_regular = df_regular.sort_values(by=['ID_sort', 'Ngày chấm công'])
    df_outside = df_outside.sort_values(by=['ID_sort', 'Ngày chấm công'])

    # Gộp lại, nhân viên thường trước
    df_sorted = pd.concat([df_regular, df_outside], ignore_index=True)

    return df_sorted.drop(columns=['ID_sort'])

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    total_duration = None  # Khởi tạo ngoài để tránh lỗi khi không có dữ liệu

    if request.method == 'POST':
        file = request.files['file']
        policy_file = request.files.get('policy_file')

        filename = file.filename.lower()
        policy_df = None

        if file and (filename.endswith('.csv') or filename.endswith('.xlsx')):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)

            try:
                # Đọc file chấm công
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath, encoding='utf-8-sig')
                elif filename.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(filepath)
                else:
                    df = pd.read_excel(filepath)
            except Exception as e:
                return f"Lỗi khi đọc file chấm công: {str(e)}"

            # Nếu có file policy -> đọc
            if policy_file and policy_file.filename.endswith('.xlsx'):
                policy_path = os.path.join(app.config['UPLOAD_FOLDER'], policy_file.filename)
                policy_file.save(policy_path)

                try:
                    policy_df = pd.read_excel(policy_path)
                except Exception as e:
                    return f"Lỗi khi đọc file policy: {str(e)}"

            # Gọi hàm xử lý
            result = process_attendance(df, policy_df)
            cache.set('attendance_data', result)

            # Ghi ra file
            save_excel(result)

        else:
            return "Chỉ hỗ trợ file .csv hoặc .xlsx"

    # GET: lọc dữ liệu từ cache
    cached_df = cache.get('attendance_data')

    if cached_df is not None:
        df = cached_df.copy()

        msnv = request.args.get('msnv', '').strip()
        name = request.args.get('name', '').strip().lower()
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        shift_types = request.args.getlist('shift_type[]')  # Lấy danh sách shift_type

        # Lọc theo loại ca
        if shift_types:
            df = df[df['Loại ca'].isin(shift_types)]
        if msnv:
            df = df[df['ID'].astype(str) == msnv]
        if name:
            df = df[df['Họ tên'].str.lower() == name]

        # Filter by date range using string comparison
        if start_date:
            try:
                # Validate date format
                pd.to_datetime(start_date)  # Ensure valid date
                df = df[df['Ngày chấm công'] >= start_date]
            except ValueError:
                return "Định dạng ngày bắt đầu không hợp lệ. Vui lòng nhập theo định dạng yyyy-mm-dd."
        if end_date:
            try:
                pd.to_datetime(end_date)  # Ensure valid date
                df = df[df['Ngày chấm công'] <= end_date]
            except ValueError:
                return "Định dạng ngày kết thúc không hợp lệ. Vui lòng nhập theo định dạng yyyy-mm-dd."

        if msnv:
            total_seconds = int(df['Thời lượng (h)'].sum() * 3600)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            total_duration = f"{hours} giờ {minutes} phút"
        
        try:
            df['ID_sort'] = df['ID'].apply(lambda x: int(str(x).split('_')[-1]) if 'OUTSIDE_' in str(x) else int(x))
        except ValueError:
            df['ID_sort'] = df['ID']  # fallback nếu có lỗi

        df = df.sort_values(by=['ID_sort', 'Ngày chấm công']).drop(columns=['ID_sort'])

        df = sort_attendance_df(df)
        result = df

    return render_template('index.html',
        tables=[result.to_html(classes='data', index=False, escape=False)] if result is not None else None,
        titles=result.columns.values if result is not None else None,
        result=result if result is not None else pd.DataFrame(),
        total_duration=total_duration if result is not None else None
    )


@app.route('/download', methods=['GET', 'POST'])
def download_excel():
    # Lấy dữ liệu
    df = cache.get('attendance_data')
    if df is None:
        return "Không có dữ liệu để tải.", 400

    # Xử lý nguồn dữ liệu đầu vào
    if request.method == 'POST':
        visible_cols_str = request.form.get('visible_columns', '')
        shift_types = request.form.getlist('shift_type[]')
        employee_id = request.form.get('employee_id', '').strip()
        name = request.form.get('name', '').strip().lower()
    else:  # GET
        visible_cols_str = request.args.get('visible_columns', '')
        shift_types = request.args.getlist('shift_type[]')
        employee_id = request.args.get('employee_id', '').strip()
        name = request.args.get('name', '').strip().lower()

    # Lọc dữ liệu nếu có shift_type hoặc ID
    df_filtered = df.copy()

    if shift_types:
        df_filtered = df_filtered[df_filtered['Loại ca'].isin(shift_types)]

    if employee_id:
        df_filtered = df_filtered[df_filtered['ID'].astype(str) == employee_id]

    # Tính thời lượng nếu có
    if 'Thời lượng (h)' in df_filtered.columns:
        df_filtered['Thời lượng'] = df_filtered['Thời lượng (h)'].apply(format_duration)

    # Chọn cột cần export
    visible_indices = list(map(int, visible_cols_str.split(','))) if visible_cols_str else []
    full_columns = df_filtered.columns.tolist()
    selected_columns = [full_columns[i] for i in visible_indices if i < len(full_columns)]
    df_final = df_filtered[selected_columns] if selected_columns else df_filtered

    # Tính tổng thời lượng (nếu lọc theo ID)
    total_duration = None
    if employee_id and 'Thời lượng (h)' in df_filtered.columns:
        total_seconds = int(df_filtered['Thời lượng (h)'].sum() * 3600)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        total_duration = f"{hours} giờ {minutes} phút"

    # Thêm dòng tổng
    if total_duration and 'Thời lượng' in df_final.columns:
        total_row = pd.DataFrame(
            [['Tổng thời lượng', total_duration]],
            columns=[df_final.columns[0], df_final.columns[-1]]
        )
        df_final = pd.concat([df_final, total_row], ignore_index=True)

    # Xuất file Excel
    output = BytesIO()
    df_final.to_excel(output, index=False)
    output.seek(0)

    file_name = (employee_id + name if employee_id else "ket_qua_loc") + '.xlsx'
    return send_file(output, download_name=file_name, as_attachment=True)


@app.route('/download', methods=['GET'])
def download_filtered_excel():
    visible_cols_str = request.args.get('visible_columns', '')
    visible_indices = list(map(int, visible_cols_str.split(','))) if visible_cols_str else []

    shift_types = request.args.getlist('shift_type[]')  # Lấy danh sách shift_type
    employee_id = request.args.get('employee_id', '').strip()
    name = request.args.get('name', '').strip().lower()

    file_name = employee_id + name

    df = cache.get('attendance_data')
    if df is None:
        return "Không có dữ liệu để tải.", 400

    df_filtered = df.copy()

    # Lọc theo loại ca (nếu có)
    if shift_types:
        df_filtered = df_filtered[df_filtered['Loại ca'].isin(shift_types)]

    # Lọc theo ID (nếu có)
    if employee_id:
        df_filtered = df_filtered[df_filtered['ID'].astype(str) == employee_id]

    # Tạo cột "Thời lượng" đẹp (giờ - phút)
    df_filtered['Thời lượng'] = df_filtered['Thời lượng (h)'].apply(format_duration)

    # Lấy đúng thứ tự cột như hiển thị HTML
    full_columns = df_filtered.columns.tolist()
    selected_columns = [full_columns[i] for i in visible_indices if i < len(full_columns)]
    df_final = df_filtered[selected_columns] if selected_columns else df_filtered

    total_duration = None
    if employee_id:
        total_seconds = int(df_filtered['Thời lượng (h)'].sum() * 3600)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        total_duration = f"{hours} giờ {minutes} phút"

    # Thêm dòng tổng thời lượng nếu có
    if total_duration and employee_id:
        # Tạo DataFrame cho dòng tổng
        total_row = pd.DataFrame([['Tổng thời lượng', total_duration] if 'Thời lượng' in df_final.columns else ['Tổng', total_duration]], 
                                columns=[df_final.columns[0], df_final.columns[-1]])
        df_final = pd.concat([df_final, total_row], ignore_index=True)

    output = BytesIO()
    df_final.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, download_name=file_name + '.xlsx', as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)