import os
from flask import Flask, request, render_template, redirect, url_for, send_file
from flask_caching import Cache
from datetime import datetime
import pandas as pd
from services.attendance_service import process_attendance
from services.excel_service import save_excel, get_excel_path

app = Flask(__name__)
df_result = pd.DataFrame()

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 60 * 60  # giữ cache 1 giờ
cache = Cache(app)


@app.route('/', methods=['GET', 'POST'])
def index():
    result = None

    if request.method == 'POST':
        file = request.files['file']
        filename = file.filename.lower()

        if file and (filename.endswith('.csv') or filename.endswith('.xlsx')):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)

            # Đọc file theo định dạng
            try:
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath, encoding='utf-8-sig')
                else:  # Excel
                    df = pd.read_excel(filepath)
            except Exception as e:
                return f"Lỗi khi đọc file: {str(e)}"

            # Xử lý dữ liệu
            result = process_attendance(df)
            cache.set('attendance_data', result)

            # Lưu kết quả ra Excel hoặc CSV
            save_excel(result)  # Hoặc: save_csv(result)

        else:
            return "Chỉ hỗ trợ file .csv hoặc .xlsx"


    # Lọc dữ liệu từ cache nếu có
    cached_df = cache.get('attendance_data')
    if cached_df is not None:
        df = cached_df.copy()

        # Lọc theo các tiêu chí
        msnv = request.args.get('msnv', '').strip()
        name = request.args.get('name', '').strip().lower()
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        shift_type = request.args.get('shift_type', '')
        if shift_type:
            df = df[df['Loại ca'].str.contains(shift_type, case=False, na=False)]

        if msnv:
            df = df[df['ID'].astype(str).str.contains(msnv)]
        if name:
            df = df[df['Họ tên'].str.lower().str.contains(name)]
        if start_date:
            df = df[df['Ngày'] >= pd.to_datetime(start_date).date()]
        if end_date:
            df = df[df['Ngày'] <= pd.to_datetime(end_date).date()]
        shift_type = request.args.get('shift_type', '')
        if shift_type:
            df = df[df['Loại ca'].str.contains(shift_type, case=False, na=False)]

        result = df

    return render_template('index.html',
                           tables=[result.to_html(classes='data')] if result is not None else None,
                           titles=result.columns.values if result is not None else None)


@app.route('/download')
def download_excel():
    path = get_excel_path()
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    else:
        return "Không tìm thấy file kết quả.", 404


if __name__ == '__main__':
    app.run(debug=True)