import re

with open('app.py', 'r') as f:
    content = f.read()

# Replace year_req with quarter_req handling
old_kpi_block = """        if year_req:
            year_int = int(year_req)
            if year_int > 2025:
                projections = {2026: 622409, 2027: 645120, 2028: 681350, 2029: 712400, 2030: 731423}
                last_val = projections.get(year_int, 0) / 4
                if prov_req:
                     last_val = last_val / 52
                last_q = pd.Timestamp(year=year_int, month=10, day=1)
            else:
                df_year = df_model[df_model['Trimestre'].dt.year == year_int]
                if prov_req:
                    df_year = df_year[df_year['Provincia'] == prov_req]
                if df_year.empty:
                    return jsonify({"error": f"No hay datos para el año {year_req}"}), 404
                last_q = df_year['Trimestre'].max()
                last_val = df_year[df_year['Trimestre'] == last_q]['Hipotecas_Total'].sum()
        else:
            last_q = df_nac.index[-1]
            last_val = float(df_nac.iloc[-1]['Hipotecas_Total'])"""

new_kpi_block = """        if year_req:
            # We are using year_req as the quarter string now, e.g., '2026-Q1'
            if 'Q' in str(year_req):
                yr, q = str(year_req).split('-Q')
                year_int = int(yr)
                q_int = int(q)
                last_q = pd.Timestamp(year=year_int, month=(q_int-1)*3 + 1, day=1)
                
                # We need to find the prediction for this exact quarter
                # It will be calculated in the forecast section, so we will assign last_val after forecast
                last_val = 0 # Placeholder, will be updated later
            else:
                year_int = int(year_req)
                df_year = df_model[df_model['Trimestre'].dt.year == year_int]
                if prov_req:
                    df_year = df_year[df_year['Provincia'] == prov_req]
                if df_year.empty:
                    return jsonify({"error": f"No hay datos para el año {year_req}"}), 404
                last_q = df_year['Trimestre'].max()
                last_val = df_year[df_year['Trimestre'] == last_q]['Hipotecas_Total'].sum()
        else:
            last_q = df_nac.index[-1]
            last_val = float(df_nac.iloc[-1]['Hipotecas_Total'])"""

content = content.replace(old_kpi_block, new_kpi_block)

old_available = "        result['available_years'] = available_years\n        result['available_provs'] = available_provs"
new_available = """        quarters = []
        for y in range(2026, 2031):
            for q in range(1, 5):
                quarters.append(f"{y}-Q{q}")
        available_years = sorted(df_model['Trimestre'].dt.year.unique().tolist(), reverse=True) + quarters
        result['available_years'] = available_years
        result['available_provs'] = available_provs"""

content = content.replace(old_available, new_available)

with open('app.py', 'w') as f:
    f.write(content)
