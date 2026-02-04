import re

def extraer_tiempo_mock(nombre_archivo):
    tiempo_encontrado = None
    
    # Limpiar extensión
    nombre_limpio = nombre_archivo.lower()
    for ext in [".gcode.3mf", ".3mf", ".gcode", ".gco"]:
        if nombre_limpio.endswith(ext):
            print(f"Removed extension {ext}")
            nombre_limpio = nombre_limpio[:-len(ext)]
            break
            
    print(f"Limpiado: {nombre_limpio}")

    # Estrategia 1: Regex Complejo
    match_complejo = re.search(r"(?i)(?:_|-)(\d{1,2}h)?(\d{1,2}m)?(?:_|-|\.|$)", nombre_limpio)
    if match_complejo:
        partes = []
        if match_complejo.group(1): partes.append(match_complejo.group(1))
        if match_complejo.group(2): partes.append(match_complejo.group(2))
        if partes:
            tiempo_encontrado = "".join(partes)

    # Estrategia 2: Regex Simple (pero con bordes)
    if not tiempo_encontrado:
         match_simple = re.search(r"(?i)(?:^|_)(\d+h\d+m|\d+h|\d+m)(?:_|$)", nombre_limpio)
         if match_simple:
             tiempo_encontrado = match_simple.group(1)

    return tiempo_encontrado

# Test Case
filename = "SAG_GRANDE_TAPA.gcode.3mf"
print(f"Testing: {filename}")
result = extraer_tiempo_mock(filename)
print(f"Result: {result}")

filename2 = "Pieza_2h45m.gcode"
print(f"Testing: {filename2}")
result2 = extraer_tiempo_mock(filename2)
print(f"Result: {result2}")
