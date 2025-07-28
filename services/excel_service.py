import os

def save_excel(df, filename='result.xlsx', folder='downloads'):
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    df.to_excel(filepath, index=False)
    return filepath

def get_excel_path(filename='result.xlsx', folder='downloads'):
    return os.path.join(folder, filename)