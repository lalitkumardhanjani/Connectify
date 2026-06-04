import csv
import os
import openpyxl
from openpyxl.worksheet.table import Table, TableStyleInfo

CSV_FILE = 'collected_emails.csv'
EXCEL_FILE = 'job_tracker.xlsx'

HEADERS = ['ID', 'Name', 'Date', 'Status', 'Timestamp', 'Email', 'Snippet']

def migrate():
    print(f"Loading data from {CSV_FILE}...")
    if not os.path.exists(CSV_FILE):
        print(f"Error: {CSV_FILE} does not exist!")
        return

    records = []
    with open(CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            records.append([
                idx,  # ID
                row.get('name', ''),
                row.get('date', ''),
                row.get('status', ''),
                row.get('timestamp', ''),
                row.get('email', ''),
                row.get('snippet', '')
            ])

    print(f"Found {len(records)} records. Writing to {EXCEL_FILE}...")
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jobs"
    
    # Write headers
    ws.append(HEADERS)
    
    # Write data
    for rec in records:
        ws.append(rec)
        
    # Format as an Excel Table
    max_row = max(ws.max_row, 1)
    ref_range = f"A1:H{max_row}"
    tab = Table(displayName="JobTrackerTable", ref=ref_range)
    style = TableStyleInfo(
        name="TableStyleLight9", 
        showFirstColumn=False,
        showLastColumn=False, 
        showRowStripes=True, 
        showColumnStripes=False
    )
    tab.tableStyleInfo = style
    ws.add_table(tab)
    
    wb.save(EXCEL_FILE)
    print(f"Successfully migrated data to {EXCEL_FILE}!")

if __name__ == '__main__':
    migrate()
