with open('app.py', 'r') as f:
    lines = f.readlines()

# Find the start of forecast block
forecast_start_idx = -1
for i, line in enumerate(lines):
    if "# ── 6. Forecast 5 años 2026-2030" in line:
        forecast_start_idx = i
        break

# Find the end of forecast block
forecast_end_idx = -1
for i in range(forecast_start_idx, len(lines)):
    if "# ── 7. Stress Test" in line or "result['forecast']" in lines[i]:
        # We need to find where the loop ends. 
        # Actually let's just find the line result['forecast'] = ...
        if "result['forecast'] =" in lines[i]:
            forecast_end_idx = i + 4 # Take a few more lines
            break

if forecast_start_idx != -1 and forecast_end_idx != -1:
    forecast_block = lines[forecast_start_idx:forecast_end_idx]
    remaining_lines = lines[:forecast_start_idx] + lines[forecast_end_idx:]
    
    # Insert forecast block before KPI calculation (around line 740)
    insert_idx = -1
    for i, line in enumerate(remaining_lines):
        if "if year_req:" in line and "We are using year_req" in remaining_lines[i+1]:
            insert_idx = i
            break
    
    if insert_idx != -1:
        new_lines = remaining_lines[:insert_idx] + forecast_block + remaining_lines[insert_idx:]
        with open('app.py', 'w') as f:
            f.writelines(new_lines)
        print("Moved forecast block successfully.")
    else:
        print("Could not find insert index.")
else:
    print("Could not find forecast block.")
