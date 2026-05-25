import re
import csv
import time
import requests
import sys

# Configuración
# Nos metemos el html de la web principal en local para no tener que hacer peticiones a la web
HTML_FILE_PATH = '/Users/fran/Documents/Proyectos máster/TFM/tinsa.html'
OUTPUT_CSV_PATH = '/Users/fran/Documents/Proyectos máster/TFM/tinsa_espana_precios.csv'
#WEB_PATH = 'https://www.tinsa.es/precio-vivienda/'
def get_province_urls(html_content):
    """Extrae nombres y URLs de provincias desde el contenido HTML."""
    # Buscamos patrones como:
    # imieAddLocationToMap(55, "Salamanca", "Provincia", 7, true, "https://www.tinsa.es/precio-vivienda/castilla-leon/salamanca/", ...
    pattern = r'imieAddLocationToMap\([^,]+,\s*"([^"]+)",\s*"Provincia",\s*[^,]+,\s*[^,]+,\s*"([^"]+)"'
    matches = re.findall(pattern, html_content)
    # Filtrar duplicados y limpiar
    unique_provinces = {}
    for name, url in matches:
        if name not in unique_provinces:
            unique_provinces[name] = url
    return unique_provinces

def extract_chart_data(content):
    """Extrae fechas y precios del contenido HTML de una página de provincia."""
    # 1. Extraer fechas (eje X)
    dates_pattern = r"categories:\s*\[(.*?)\]"
    dates_match = re.search(dates_pattern, content, re.DOTALL)
    
    if not dates_match:
        return None, None

    raw_dates = dates_match.group(1)
    dates = [d.strip().strip("'").strip('"') for d in raw_dates.split(',')]

    # 2. Extraer precios
    data_pattern = r"data:\s*\[([\d\.,\s-]+)\]"
    matches = re.findall(data_pattern, content)

    prices = []
    found = False
    for match in matches:
        try:
            current_data = [float(x.strip()) for x in match.split(',')]
            # Heurística: longitud similar a fechas y valores > 100
            if len(current_data) == len(dates) and all(x > 100 for x in current_data):
                prices = current_data
                found = True
                break
        except ValueError:
            continue
            
    if found:
        return dates, prices
    return None, None

def main():
    print("--- Tinsa Scraper Global ---")
    
    # 1. Leer archivo local para descubrimiento
    try:
        with open(HTML_FILE_PATH, 'r', encoding='utf-8') as f:
            local_content = f.read()
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo base en {HTML_FILE_PATH}")
        return

    provinces = get_province_urls(local_content)
    print(f"Se encontraron {len(provinces)} provincias para procesar.")

    if not provinces:
        print("No se encontraron URLs de provincias. Revisa el archivo HTML.")
        return

    # 2. Iterar y extraer
    all_data = []
    processed_count = 0
    
    # Headers para requests
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    for province_name, url in provinces.items():
        print(f"Procesando: {province_name}...", end=" ", flush=True)
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                dates, prices = extract_chart_data(response.text)
                
                if dates and prices:
                    for date, price in zip(dates, prices):
                        all_data.append([province_name, date, price])
                    print(f"OK ({len(prices)} datos)")
                    processed_count += 1
                else:
                    print("Error: No se encontraron datos de gráfica.")
            else:
                print(f"Error HTTP: {response.status_code}")
                
        except Exception as e:
            print(f"Excepción: {e}")
        
        # Respetar al servidor
        time.sleep(1)

    # 3. Guardar CSV global
    if all_data:
        with open(OUTPUT_CSV_PATH, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Provincia', 'Trimestre', 'Precio_m2'])
            writer.writerows(all_data)
        
        print(f"\n¡Completado! Se extrajeron datos de {processed_count} provincias.")
        print(f"Archivo guardado en: {OUTPUT_CSV_PATH}")
    else:
        print("\nNo se extrajeron datos.")

if __name__ == "__main__":
    main()
