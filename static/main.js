document.querySelectorAll('.toggle-col').forEach(function (checkbox) {
    checkbox.addEventListener('change', function () {
        const colIndex = parseInt(this.getAttribute('data-col'));
        const display = this.checked ? '' : 'none';

        document.querySelectorAll('table.dataframe tr').forEach(function (row) {
            const cells = row.querySelectorAll('th, td');
            if (cells[colIndex]) {
                cells[colIndex].style.display = display;
            }
        });
    });
});

document.getElementById('download-form').addEventListener('submit', function (e) {
    const visibleCols = [];
    document.querySelectorAll('.toggle-col:checked').forEach(checkbox => {
        const colIndex = parseInt(checkbox.getAttribute('data-col'));
        visibleCols.push(colIndex);
    });
    console.log('visibleCols:', visibleCols); // Gỡ lỗi
    document.getElementById('visible-columns').value = visibleCols.join(',');
});

// Gán cột hiển thị vào form lọc (GET)
document.getElementById('download-filter-form').addEventListener('submit', function (e) {
    const visibleCols = [];
    document.querySelectorAll('.toggle-col:checked').forEach(checkbox => {
        const colIndex = parseInt(checkbox.getAttribute('data-col'));
        visibleCols.push(colIndex);
    });
    document.getElementById('visible_columns_filter_input').value = visibleCols.join(',');
});

function toggleVisibility(id) {
    const element = document.getElementById(id);
    if (element.style.display === "none") {
        element.style.display = "block";
    } else {
        element.style.display = "none";
    }
}

function updatePerPage(perPage) {
        console.log('Selected per_page:', perPage);
        const validPerPage = [10, 25, 50, 100];
        if (!validPerPage.includes(parseInt(perPage))) {
            console.error('Invalid per_page value:', perPage);
            return;
        }
        const params = new URLSearchParams(window.location.search);
        params.set('per_page', perPage);
        params.set('page', 1);
        const newUrl = '{{ url_for("index") }}?' + params.toString();
        console.log('Navigating to:', newUrl);
        window.location.href = newUrl;
    }

document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll('.toggle-col').forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            const colIndex = parseInt(this.getAttribute('data-col'));
            const display = this.checked ? '' : 'none';

            document.querySelectorAll('table.dataframe tr').forEach(function (row) {
                const cells = row.querySelectorAll('th, td');
                if (cells[colIndex]) {
                    cells[colIndex].style.display = display;
                }
            });
        });

        // Áp dụng trạng thái ngay khi load
        checkbox.dispatchEvent(new Event('change'));
    });
});
