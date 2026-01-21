// HR System JavaScript
/*
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Confirm delete actions
    var deleteButtons = document.querySelectorAll('.btn-delete');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to delete this item?')) {
                e.preventDefault();
            }
        });
    });

    // Form validation
    var forms = document.querySelectorAll('.needs-validation');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Date picker initialization
    var dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach(function(input) {
        // Set max date to today for certain fields
        if (input.name === 'date_hired' || input.name === 'date') {
            input.max = new Date().toISOString().split('T')[0];
        }
    });

    // Time picker initialization
    var timeInputs = document.querySelectorAll('input[type="time"]');
    timeInputs.forEach(function(input) {
        // Set current time as default
        if (!input.value) {
            var now = new Date();
            var timeString = now.getHours().toString().padStart(2, '0') + ':' + 
                           now.getMinutes().toString().padStart(2, '0');
            input.value = timeString;
        }
    });

    // Auto-calculate days for leave requests
    var startDateInput = document.querySelector('input[name="start_date"]');
    var endDateInput = document.querySelector('input[name="end_date"]');
    var daysInput = document.querySelector('input[name="days_requested"]');

    if (startDateInput && endDateInput && daysInput) {
        function calculateDays() {
            var startDate = new Date(startDateInput.value);
            var endDate = new Date(endDateInput.value);
            
            if (startDate && endDate && endDate >= startDate) {
                var timeDiff = endDate.getTime() - startDate.getTime();
                var daysDiff = Math.ceil(timeDiff / (1000 * 3600 * 24)) + 1;
                daysInput.value = daysDiff;
            }
        }

        startDateInput.addEventListener('change', calculateDays);
        endDateInput.addEventListener('change', calculateDays);
    }

    // Search functionality
    var searchInputs = document.querySelectorAll('.search-input');
    searchInputs.forEach(function(input) {
        input.addEventListener('input', function() {
            var searchTerm = this.value.toLowerCase();
            var table = this.closest('.card').querySelector('table');
            
            if (table) {
                var rows = table.querySelectorAll('tbody tr');
                rows.forEach(function(row) {
                    var text = row.textContent.toLowerCase();
                    if (text.includes(searchTerm)) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                });
            }
        });
    });

    // Attendance status change handler
    var statusSelects = document.querySelectorAll('select[name="status"]');
    statusSelects.forEach(function(select) {
        select.addEventListener('change', function() {
            var timeInInput = this.closest('form').querySelector('input[name="time_in"]');
            var timeOutInput = this.closest('form').querySelector('input[name="time_out"]');
            
            if (this.value === 'Absent') {
                if (timeInInput) timeInInput.disabled = true;
                if (timeOutInput) timeOutInput.disabled = true;
            } else {
                if (timeInInput) timeInInput.disabled = false;
                if (timeOutInput) timeOutInput.disabled = false;
            }
        });
    });

    // Department filter change handler
    var departmentSelects = document.querySelectorAll('select[name="department"]');
    departmentSelects.forEach(function(select) {
        select.addEventListener('change', function() {
            this.closest('form').submit();
        });
    });

    // Status filter change handler
    var statusSelects = document.querySelectorAll('select[name="status"]');
    statusSelects.forEach(function(select) {
        select.addEventListener('change', function() {
            this.closest('form').submit();
        });
    });

    // Export functionality
    var exportButtons = document.querySelectorAll('.btn-export');
    exportButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            var format = this.dataset.format || 'csv';
            var table = this.closest('.card').querySelector('table');
            
            if (table) {
                exportTable(table, format);
            }
        });
    });

    // Print functionality
    var printButtons = document.querySelectorAll('.btn-print');
    printButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            window.print();
        });
    });
});

// Export table to CSV
function exportTable(table, format) {
    var csv = [];
    var rows = table.querySelectorAll('tr');
    
    for (var i = 0; i < rows.length; i++) {
        var row = [], cols = rows[i].querySelectorAll('td, th');
        
        for (var j = 0; j < cols.length; j++) {
            var text = cols[j].innerText.replace(/"/g, '""');
            row.push('"' + text + '"');
        }
        
        csv.push(row.join(','));
    }
    
    var csvFile = new Blob([csv.join('\n')], { type: 'text/csv' });
    var downloadLink = document.createElement('a');
    downloadLink.download = 'export.csv';
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
}

// Show loading spinner
function showLoading(element) {
    var spinner = document.createElement('div');
    spinner.className = 'spinner';
    spinner.id = 'loading-spinner';
    element.appendChild(spinner);
}

// Hide loading spinner
function hideLoading() {
    var spinner = document.getElementById('loading-spinner');
    if (spinner) {
        spinner.remove();
    }
}

// Show success message
function showSuccess(message) {
    showAlert(message, 'success');
}

// Show error message
function showError(message) {
    showAlert(message, 'danger');
}

// Show alert message
function showAlert(message, type) {
    var alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-' + type + ' alert-dismissible fade show';
    alertDiv.innerHTML = message + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
    
    var container = document.querySelector('.container-fluid');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-hide after 5 seconds
        setTimeout(function() {
            var bsAlert = new bootstrap.Alert(alertDiv);
            bsAlert.close();
        }, 5000);
    }
}

// Format currency
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-PH', {
        style: 'currency',
        currency: 'PHP'
    }).format(amount);
}

// Format date
function formatDate(dateString) {
    var date = new Date(dateString);
    return date.toLocaleDateString('en-PH', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

// Format time
function formatTime(timeString) {
    var time = new Date('1970-01-01T' + timeString);
    return time.toLocaleTimeString('en-PH', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// AJAX helper function
function makeRequest(url, method, data, callback) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                var response = JSON.parse(xhr.responseText);
                if (callback) callback(null, response);
            } else {
                if (callback) callback(new Error('Request failed'), null);
            }
        }
    };
    
    if (data) {
        xhr.send(JSON.stringify(data));
    } else {
        xhr.send();
    }
}
*/
// Function to toggle password visibility


<script>
document.addEventListener("DOMContentLoaded", function () {
  const logoutBtn = document.getElementById("logoutBtn");

  logoutBtn.addEventListener("click", function (e) {
    e.preventDefault(); // Prevent default action

    Swal.fire({
      title: "Are you sure?",
      text: "You will be logged out and might need to login again!",
      icon: "warning",
      showCancelButton: true,
      confirmButtonColor: "#3085d6",
      cancelButtonColor: "#d33",
      confirmButtonText: "Yes, logout!"
    }).then((result) => {
      if (result.isConfirmed) {
        // Redirect to logout route
        window.location.href = "{{ url_for('auth.logout') }}";
      }
    });
  });
});
</script>