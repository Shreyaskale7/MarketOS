import re

with open('marketos_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace GET requests
text = re.sub(r'await fetch\(`\$\{API\}(.*?)\`\)\.then\(r=>r\.json\(\)\)', r'await fetchAPI(`\1`)', text)
# Replace POST requests
text = text.replace('await fetch(`${API}/api/run/daily`,{method:\'POST\'})', 'await fetchAPI(`/api/run/daily`, {method:\'POST\'})')
# Replace initApp
text = text.replace('window.onload=initApp;', 'window.onload=initAuth;')
text = text.replace('window.onload = initApp;', 'window.onload = initAuth;')

with open('marketos_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(text)
