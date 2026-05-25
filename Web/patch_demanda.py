import re

with open('app.py', 'r') as f:
    content = f.read()

# Modify /demanda to use df_prov_preds
new_forecast_logic = """
        # ── 6. Forecast 5 años 2026-2030 (RF Recursivo + SARIMA Provincial) ────────────
        last_data = df_model.sort_values('Trimestre').groupby('Provincia').last().reset_index()
        forecast_qs = pd.date_range(start='2026-01-01', end='2030-12-31', freq='QS')
        forecast_vals = []
        
        current_preds = last_data.copy()
        
        # Mapear predicciones SARIMA provinciales para usar en RF (si existen)
        if not df_prov_preds.empty:
            pred_pivot = df_prov_preds.pivot_table(index=['provincia', 'trimestre'], columns='variable', values='valor').reset_index()
        else:
            pred_pivot = pd.DataFrame()
            
        for fq in forecast_qs:
            q_str = f"{fq.year}Q{(fq.month-1)//3 + 1}"
            
            row_data = current_preds[features].copy()
            row_data['trimestre_num'] = fq.quarter
            row_data['Provincia'] = current_preds['Provincia']
            
            for idx, row in row_data.iterrows():
                prov = row['Provincia']
                
                if not pred_pivot.empty:
                    macro_q = pred_pivot[(pred_pivot['provincia'] == prov) & (pred_pivot['trimestre'] == q_str)]
                else:
                    macro_q = pd.DataFrame()
                
                for col_feat in features:
                    # Inyectar valores provinciales SARIMA
                    macro_name = col_feat.replace('_lag1', '').replace('_yoy', '').replace('_lag4', '').replace('_rmean4', '')
                    if not macro_q.empty and macro_name in macro_q.columns:
                        row_data.at[idx, col_feat] = macro_q[macro_name].values[0]
            
            X_pred = row_data[features]
            preds_q = rf.predict(X_pred)
            
            if prov_req:
                mask = current_preds['Provincia'] == prov_req
                forecast_vals.append(round(float(preds_q[mask].sum())))
            else:
                forecast_vals.append(round(float(preds_q.sum())))
            
            # Simple recursive update for lag1
            if 'Hipotecas_Total_lag1' in current_preds.columns:
                current_preds['Hipotecas_Total_lag1'] = preds_q
                
        result['forecast'] = {
            'labels': [d.strftime('%Y-%m') for d in forecast_qs],
            'values': forecast_vals,
        }
"""

old_forecast_logic_start = "# ── 6. Forecast 5 años 2026-2030"
old_forecast_logic_end = "# ── 7. Stress Test"

start_idx = content.find(old_forecast_logic_start)
end_idx = content.find(old_forecast_logic_end)

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_forecast_logic + "\n        " + content[end_idx:]

with open('app.py', 'w') as f:
    f.write(content)
