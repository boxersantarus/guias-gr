import os
import fitz  # PyMuPDF
import qrcode
from flask import Flask, request, send_file, render_template_string, render_template, redirect
from bs4 import BeautifulSoup
from io import BytesIO
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import json
import uuid

# Establecer la ruta de la biblioteca ZBar
os.environ['LD_LIBRARY_PATH'] = os.path.join(os.getcwd(), 'lib/zbar')

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# HTML base (consulta.html modificable)
with open("consulta.html", "r", encoding="utf-8") as f:
    HTML_TEMPLATE = f.read()

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/procesar', methods=['POST'])
def procesar():
    file = request.files['pdf_file']
    if not file:
        return "No se cargó ningún archivo."

    pdf_bytes = file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # Extraer Código de Verificación
    text = "\n".join(page.get_text() for page in doc)
    #print(text)
    cod_verif = extraer_codigo_verificacion(text)
    if not cod_verif:
        return "No se encontró el Código de Verificación."

    json_file_path = "config.json"
    try:
        with open(json_file_path, 'r') as file:
            config = json.load(file)
        base_url = config.get("base_url")
        if not base_url:
            raise ValueError("La clave 'base_url' no está en el archivo JSON.")

        print(base_url)
    except FileNotFoundError:
        print(f"El archivo {json_file_path} no se encontró.")
    except json.JSONDecodeError:
        print("Error al parsear el archivo JSON.")
    except ValueError as e:
        print(e)

    qr_url = f"{base_url}/html/{cod_verif}"
    qr_url_html = f"{base_url}/guias/validar/{cod_verif}"

    campos = extraer_campos(text, qr_url)
    os.makedirs("data", exist_ok=True)
    with open(f"data/{cod_verif}.json", "w", encoding="utf-8") as f:
        json.dump(campos, f, indent=2, ensure_ascii=False)

    
    #output_pdf_path = os.path.join(OUTPUT_FOLDER, f"{cod_verif}.pdf")
    #reemplazar_qr(doc, qr_url, pdf_bytes)
    #doc.save(output_pdf_path)

    # Modificar HTML
    html_mod = modificar_html(cod_verif)
    html_output_path = os.path.join(OUTPUT_FOLDER, f"{cod_verif}.html")
    with open(html_output_path, 'w', encoding='utf-8') as f:
        f.write(html_mod)

    #return f"PDF generado con éxito. <a href='/descargar/{cod_verif}'>Descargar PDF</a> | <a href='/html/{cod_verif}'>Ver HTML</a>"
    return render_template("resultado.html", codigo=cod_verif)


def extraer_codigo_verificacion(text):
    for line in text.split("\n"):
        if "Código de Verificación" in line:
            parts = line.split(":")
            if len(parts) == 2:
                return parts[1].strip()
    return None

def find_qr_in_pdf_bytes(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # alta resolución
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
        img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n > 1 else img

        decoded_objects = decode(img_gray)

        for obj in decoded_objects:
            x, y, w, h = obj.rect
            qr_rect = fitz.Rect(x, y, x + w, y + h)

            # Mapear coordenadas de la imagen a coordenadas de la página
            page_rect = page.rect
            img_rect = fitz.Rect(0, 0, pix.width, pix.height)

            # Calcular factor de escala
            scale_x = page_rect.width / img_rect.width
            scale_y = page_rect.height / img_rect.height
            # Convertir a coordenadas de página
            qr_page_rect = fitz.Rect(
                qr_rect.x0 * scale_x,
                qr_rect.y0 * scale_y,
                qr_rect.x1 * scale_x,
                qr_rect.y1 * scale_y
            )
            doc.close()
            return qr_page_rect  # retorna el primero que encuentra

    doc.close()
    return None

def reemplazar_qr(doc, url, original_bytes):
    qr_img = qrcode.make(url)
    qr_bytes = BytesIO()
    qr_img.save(qr_bytes, format='PNG')
    qr_bytes.seek(0)
    qr_rect = find_qr_in_pdf_bytes(original_bytes)
    print(qr_rect)
    page = doc[0]
    #page = 0
    print(f"page = {page}")
    if qr_rect:
        page.draw_rect(qr_rect, color=(1,1,1), fill=(1,1,1))  # cubre QR viejo
        page.insert_image(qr_rect, stream=qr_bytes)
    else:
        # fallback manual
        fallback = fitz.Rect(400, 620, 540, 760)
        page.draw_rect(fallback, color=(1,1,1), fill=(1,1,1))
        page.insert_image(fallback, stream=qr_bytes)


def eliminar_secciones(doc):
    for page in doc:
        blocks = page.get_text("dict")['blocks']
        for b in blocks:
            if 'lines' in b:
                for l in b['lines']:
                    for s in l['spans']:
                        if any(p in s['text'].upper() for p in ["INFORMACIÓN PRODUCTOS", "INFORMACIÓN DETALLADA"]):
                            rect = fitz.Rect(b['bbox'])
                            page.add_redact_annot(rect, fill=(1,1,1))
        page.apply_redactions()

def modificar_html(codigo):
    soup = BeautifulSoup(HTML_TEMPLATE, 'html.parser')
    botones = soup.find_all('a', href=True)
    for boton in botones:
        if 'verguiapdf/?type=general' in boton['href']:
            boton['href'] = f"/descargar/{codigo}"
    return str(soup)

@app.route('/descargar/<codigo>')
def descargar_pdf(codigo):
    path = os.path.join(OUTPUT_FOLDER, f"{codigo}.pdf")
    return send_file(path, as_attachment=True)

@app.route('/html/<codigo>')
def ver_html(codigo):
    path = os.path.join(OUTPUT_FOLDER, f"{codigo}.html")
    with open(path, encoding='utf-8') as f:
        return render_template_string(f.read())


@app.route('/editar/<codigo>', methods=["GET", "POST"])
def editar(codigo):
    
    json_path = f"data/{codigo}.json"
    if not os.path.exists(json_path):
        return "Datos no encontrados", 404

    if request.method == "POST":
        claves = request.form.getlist("clave")
        valores = request.form.getlist("valor")
        nuevos_datos = []

        for i, clave in enumerate(claves):
            if clave in ["logo", "img_firma"] and f"archivo_{i}" in request.files:
                archivo = request.files[f"archivo_{i}"]
                if archivo and archivo.filename.lower().endswith(".png"):
                    os.makedirs("static/guias", exist_ok=True)
                    ruta = f"static/guias/{codigo}_{clave}_{uuid.uuid4().hex[:6]}.png"
                    archivo.save(ruta)
                    valor = ruta  # Guarda la ruta como valor
                else:
                    valor = valores[i]  # Si no subió nueva imagen, conserva la anterior
            else:
                valor = valores[i]
            nuevos_datos.append((clave, valor))

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(nuevos_datos, f, indent=2, ensure_ascii=False)

        return redirect(request.form.get("from_url", f"/html/{codigo}"))

    with open(json_path, encoding='utf-8') as f:
        datos = json.load(f)  # lista de pares clave-valor
    return render_template("editar.html", codigo=codigo, datos=datos)


#def extraer_campos(texto, qr):
#    print(texto)
#    campos = []  # lista de tuplas (clave, valor)
#    for linea in texto.split("\n"):
#        if ":" in linea:
#            clave, valor = linea.split(":", 1)
#            campos.append((clave.strip(), valor.strip()))
#    clave, valor = "logo",""
#    campos.append((clave.strip(), valor.strip()))
#    clave, valor = "img_firma",""
#   campos.append((clave.strip(), valor.strip()))
#    clave, valor = "firmante",""
#    campos.append((clave.strip(), valor.strip()))
#    clave, valor = "codigo_qr",qr
#    campos.append((clave.strip(), valor.strip()))
#    return campos
def extraer_campos(texto, qr):
    print(texto)
    campos = []  # Lista de tuplas (clave, valor)
    lineas = texto.split("\n")
    clave_actual = None
    valor_actual = []
    firmante = ""  # Variable para capturar el firmante

    # Lista de textos a ignorar
    ignorar = [
        "INFORMACIÓN",
        "PRODUCTOS",
        "OBSERVACIONES",
        "DETALLADA",
        "INFORMACIÓN AGENTE DE LA CADENA VENDEDOR",
        "INFORMACIÓN AGENTE DE LA CADENA COMPRADOR",
        "INFORMACIÓN TRANSPORTE",
        "VIGENTE",
        "VENDEDOR",
        "COMPRADOR",
        "Para validar la autenticidad de esta guía puede consultar en la",
        "página https://sigdi.sicom.gov.co/guias/consulta/ O por medio",
        "del siguiente código QR"
    ]

    for i, linea in enumerate(lineas):
        if any(texto_ignorar in linea for texto_ignorar in ignorar):
            continue  # Ignorar líneas con textos específicos

        # Detectar firmante como línea anterior a "Firmado:"
        if "Firmado:" in linea and i > 0:
            firmante = lineas[i - 1].strip()

        if ":" in linea:  # Nueva clave encontrada
            if clave_actual:  # Si hay una clave anterior, guardamos el campo actual
                campos.append((clave_actual.strip(), " ".join(valor_actual).strip()))
            
            clave_actual, valor = linea.split(":", 1)

            # Excepción para "Precintos instalados:"
            if clave_actual.strip() == "Precintos instalados":
                campos.append((clave_actual.strip(), valor.strip()))
                clave_actual = None  # Reiniciar para evitar acumulación
                valor_actual = []
            else:
                valor_actual = [valor.strip()]  # Comenzamos a acumular el valor
        elif clave_actual:  # Línea sin ":", asumimos que es continuación del valor
            valor_actual.append(linea.strip())

    # Agregar el último campo acumulado
    if clave_actual:
        campos.append((clave_actual.strip(), " ".join(valor_actual).strip()))

    # Agregar campos adicionales
    campos.append(("logo", ""))
    campos.append(("img_firma", ""))
    campos.append(("firmante", firmante))
    campos.append(("codigo_qr", qr))

    return campos


def obtener_valor_definido(datos, clave):
    for item in datos:
        if item[0] == clave:
            return item[1]
    return None  # Devuelve None si la clave no se encuentra

def obtener_llave(datos, posicion):
    if posicion < 0 or posicion >= len(datos):
        return "Índice fuera de rango."
    
    clave, valor = datos[posicion]
    return f"{clave}: "

def obtener_valor(datos, posicion):
    if posicion < 0 or posicion >= len(datos):
        return "Índice fuera de rango."
    
    clave, valor = datos[posicion]
    return f"{valor}"

def generar_pdf_desde_plantilla(json_path, salida_path, plantilla_path="plantilla.pdf"):
    import fitz
    import os

    if not os.path.exists(json_path) or not os.path.exists(plantilla_path):
        raise FileNotFoundError("Archivo JSON o plantilla no encontrados.")

    with open(json_path, encoding="utf-8") as f:
        datos = json.load(f)
    print(datos)

    doc = fitz.open(plantilla_path)
    page = doc[0]  # Usamos la primera página
    Ix = 35
    Iy = 14
    font_bold = fitz.Font(fontname="times-bold")  # Fuente en negrita
    # Encabezado
    if obtener_valor_definido(datos, 'logo'):
        x = 410
        y = 10
        img_rect = fitz.Rect(x, y, x + 180, y + 80)
        page.insert_image(img_rect, filename=obtener_valor_definido(datos, 'logo'))
    
    # Información General
    x, y = Ix, 140  # Coordenadas iniciales para texto 
    for i in range(12): 
        x = Ix
        y = y + Iy
        page.insert_text((x, y), obtener_llave(datos, i), fontsize=10, fontname='times-bold')
        ancho_llave = font_bold.text_length(obtener_llave(datos, i), fontsize=10)
        if len(obtener_valor(datos, i)) > 20:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i)[:20], fontsize=9)
            x = Ix
            y = y + Iy
            page.insert_text((x, y), obtener_valor(datos, i)[20:], fontsize=9)
        else:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i), fontsize=9)
    
    # Codigo QR
    x, y  = 100, 327
    codqr = obtener_valor_definido(datos, 'codigo_qr')
    qr_img = qrcode.make(codqr)
    qr_bytes = BytesIO()
    qr_img.save(qr_bytes, format='PNG')
    qr_bytes.seek(0)
    fallback = fitz.Rect(x, y, x + 115, y + 115)
    page.draw_rect(fallback, color=(1,1,1), fill=(1,1,1))
    page.insert_image(fallback, stream=qr_bytes)

    # Información de Productos
    x, y  = Ix, 550
    for i in range(12, 15):
        x = Ix
        y = y + Iy
        page.insert_text((x, y), obtener_llave(datos, i), fontsize=10, fontname='times-bold')
        ancho_llave = font_bold.text_length(obtener_llave(datos, i), fontsize=10)
        if len(obtener_valor(datos, i)) > 20:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i)[:20], fontsize=9)
            x = Ix
            y = y + Iy
            page.insert_text((x, y), obtener_valor(datos, i)[20:], fontsize=9)
        else:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i), fontsize=9)
    # Información Detallada
    # INFORMACIÓN AGENTE DE LA CADENA VENDEDOR
    x, y = 317, 158
    page.insert_text((x, y), "INFORMACIÓN AGENTE DE LA CADENA", fontsize=11, fontname='helv')
    page.insert_text((x, y), "INFORMACIÓN AGENTE DE LA CADENA", fontsize=11, fontname='helv')
    page.insert_text((x, y), "INFORMACIÓN AGENTE DE LA CADENA", fontsize=11, fontname='helv')
    y = y + Iy
    page.insert_text((x, y), "VENDEDOR", fontsize=11, fontname='helv')
    page.insert_text((x, y), "VENDEDOR", fontsize=11, fontname='helv')
    page.insert_text((x, y), "VENDEDOR", fontsize=11, fontname='helv')
    Ix = 317
    y = y + Iy - 15
    for i in range(15, 25):
        x = Ix
        y = y + Iy - 1
        page.insert_text((x, y), obtener_llave(datos, i), fontsize=10, fontname='times-bold')
        ancho_llave = font_bold.text_length(obtener_llave(datos, i), fontsize=10)
        ancho_valor = font_bold.text_length(obtener_valor(datos, i), fontsize=9)
        if ancho_llave + ancho_valor > 240:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i)[:11], fontsize=9)
            x = Ix
            y = y + Iy
            page.insert_text((x, y), obtener_valor(datos, i)[11:], fontsize=9)
        else:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i), fontsize=9)
    # INFORMACIÓN AGENTE DE LA CADENA COMPRADOR
    x, y = 315, 338
    page.insert_text((x, y), "INFORMACIÓN AGENTE DE LA CADENA", fontsize=11, fontname='helv')
    page.insert_text((x, y), "INFORMACIÓN AGENTE DE LA CADENA", fontsize=11, fontname='helv')
    page.insert_text((x, y), "INFORMACIÓN AGENTE DE LA CADENA", fontsize=11, fontname='helv')
    y = y + Iy
    page.insert_text((x, y), "COMPRADOR", fontsize=11, fontname='helv')
    page.insert_text((x, y), "COMPRADOR", fontsize=11, fontname='helv')
    page.insert_text((x, y), "COMPRADOR", fontsize=11, fontname='helv')
    Ix = 315
    y = y + Iy - 8
    for i in range(25, 34):
        x = Ix
        y = y + Iy 
        page.insert_text((x, y), obtener_llave(datos, i), fontsize=10, fontname='times-bold')
        ancho_llave = font_bold.text_length(obtener_llave(datos, i), fontsize=10)
        ancho_valor = font_bold.text_length(obtener_valor(datos, i), fontsize=9)
        #print("ancho llave=",ancho_llave," - ancho valor=",ancho_valor)
        if ancho_llave + ancho_valor > 240:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i)[:10], fontsize=9)
            x = Ix
            y = y + Iy
            page.insert_text((x, y), obtener_valor(datos, i)[10:], fontsize=9)
        else:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i), fontsize=9)

    # INFORMACIÓN TRANSPORTE
    x, y = 315, 520
    page.insert_text((x, y), "INFORMACIÓN TRANSPORTE", fontsize=11, fontname='helv')
    page.insert_text((x, y), "INFORMACIÓN TRANSPORTE", fontsize=11, fontname='helv')
    page.insert_text((x, y), "INFORMACIÓN TRANSPORTE", fontsize=11, fontname='helv')    
    y = y + Iy - 8
    for i in range(34, 44):
        x = Ix
        y = y + Iy 
        page.insert_text((x, y), obtener_llave(datos, i), fontsize=10, fontname='times-bold')
        ancho_llave = font_bold.text_length(obtener_llave(datos, i), fontsize=10)
        ancho_valor = font_bold.text_length(obtener_valor(datos, i), fontsize=9)
        #print("ancho llave=",ancho_llave," - ancho valor=",ancho_valor)
        if ancho_llave + ancho_valor > 250:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i)[:20], fontsize=9)
            x = Ix
            y = y + Iy
            page.insert_text((x, y), obtener_valor(datos, i)[20:], fontsize=9)
        else:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i), fontsize=9)

    # PASAMOS A LA 2DA PAGINA
    page = doc[1] 
    # Firma
    if obtener_valor_definido(datos, 'img_firma'):
        x = 380
        y = 10
        img_rect = fitz.Rect(x, y, x + 100, y + 70)
        page.insert_image(img_rect, filename=obtener_valor_definido(datos, 'img_firma'))
    # Firmante
    x, y = 340, 90
    page.insert_text((x, y), obtener_valor_definido(datos, "firmante"), fontsize=10, fontname='times-bold')
    x = x + 30
    y = y + Iy
    page.insert_text((x, y), obtener_llave(datos, 44), fontsize=9, fontname='helv')
    ancho_llave = font_bold.text_length(obtener_llave(datos, 44), fontsize=10)
    x = x + ancho_llave - 5 
    page.insert_text((x, y), obtener_valor(datos, 44), fontsize=9, fontname='helv')
    x = 370
    y = y + Iy
    page.insert_text((x, y), obtener_llave(datos, 45), fontsize=9, fontname='helv')
    ancho_llave = font_bold.text_length(obtener_llave(datos, 45), fontsize=10)
    x = x + ancho_llave - 5 
    page.insert_text((x, y), obtener_valor(datos, 45), fontsize=9, fontname='helv')
    
    doc.save(salida_path)
    doc.close()

def generar_pdf_desde_plantilla1(json_path, salida_path, plantilla_path="plantilla.pdf"):
    import fitz
    import os

    if not os.path.exists(json_path) or not os.path.exists(plantilla_path):
        raise FileNotFoundError("Archivo JSON o plantilla no encontrados.")

    with open(json_path, encoding="utf-8") as f:
        datos = json.load(f)
    #print(datos)

    doc = fitz.open(plantilla_path)
    page = doc[0]  # Usamos la primera página
    Ix = 35
    Iy = 14
    font_bold = fitz.Font(fontname="times-bold")  # Fuente en negrita
    # Encabezado
    if obtener_valor_definido(datos, 'logo'):
        x = 410
        y = 10
        img_rect = fitz.Rect(x, y, x + 180, y + 80)
        page.insert_image(img_rect, filename=obtener_valor_definido(datos, 'logo'))
    
    # Información General
    x, y = Ix, 140  # Coordenadas iniciales para texto 
    for i in range(12): 
        x = Ix
        y = y + Iy
        page.insert_text((x, y), obtener_llave(datos, i), fontsize=10, fontname='times-bold')
        ancho_llave = font_bold.text_length(obtener_llave(datos, i), fontsize=10)
        if len(obtener_valor(datos, i)) > 20:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i)[:20], fontsize=9)
            x = Ix
            y = y + Iy
            page.insert_text((x, y), obtener_valor(datos, i)[20:], fontsize=9)
        else:
            x = x + ancho_llave
            page.insert_text((x, y), obtener_valor(datos, i), fontsize=9)
    
    # Codigo QR
    x, y  = 100, 327
    codqr = obtener_valor_definido(datos, 'codigo_qr')
    qr_img = qrcode.make(codqr)
    qr_bytes = BytesIO()
    qr_img.save(qr_bytes, format='PNG')
    qr_bytes.seek(0)
    fallback = fitz.Rect(x, y, x + 115, y + 115)
    page.draw_rect(fallback, color=(1,1,1), fill=(1,1,1))
    page.insert_image(fallback, stream=qr_bytes)

    doc.save(salida_path)
    doc.close()

@app.route("/generar_pdf/<codigo>")
def generar_pdf_plantilla(codigo):
    json_path = f"data/{codigo}.json"
    salida_path = f"outputs/{codigo}_completo.pdf"
    plantilla_path = "plantilla.pdf"
    try:
        generar_pdf_desde_plantilla(json_path, salida_path, plantilla_path)
        return send_file(salida_path, as_attachment=True)
    except Exception as e:
        return f"Error al generar el PDF: {str(e)}", 500

@app.route("/generar_pdf_reducido/<codigo>")
def generar_pdf_plantilla1(codigo):
    json_path = f"data/{codigo}.json"
    salida_path = f"outputs/{codigo}.pdf"
    plantilla_path = "plantilla1.pdf"
    try:
        generar_pdf_desde_plantilla1(json_path, salida_path, plantilla_path)
        return send_file(salida_path, as_attachment=True)
    except Exception as e:
        return f"Error al generar el PDF: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)