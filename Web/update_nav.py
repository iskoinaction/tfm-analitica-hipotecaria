import os
import glob

html_files = glob.glob('templates/*.html')
nav_item = '                <li><a href="/econometria">Econometría</a></li>'
for fpath in html_files:
    with open(fpath, 'r') as f:
        content = f.read()
    
    # Check if econometria is already there
    if 'href="/econometria"' not in content:
        # We find the Demanda link and insert after it
        content = content.replace('<li><a href="/demanda">Demanda</a></li>', 
                                  '<li><a href="/demanda">Demanda</a></li>\n' + nav_item)
        content = content.replace('<li><a href="/demanda" class="active">Demanda</a></li>', 
                                  '<li><a href="/demanda" class="active">Demanda</a></li>\n' + nav_item)
        with open(fpath, 'w') as f:
            f.write(content)
        print(f"Updated {fpath}")
