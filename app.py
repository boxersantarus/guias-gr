import os
import fitz  # PyMuPDF
import qrcode
from flask import Flask, request, send_file, render_template_string, render_template, redirect
from bs4 import BeautifulSoup
from io import BytesIO
import json
import uuid
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

app = Flask(__name__)
OUTPUT_FOLDER = 'outputs'
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

    qr_url = f"{base_url}/guias/{cod_verif}.html"

    campos = extraer_campos(text, qr_url)
    os.makedirs("data", exist_ok=True)
    with open(f"data/{cod_verif}.json", "w", encoding="utf-8") as f:
        json.dump(campos, f, indent=2, ensure_ascii=False)

    # Modificar HTML
    html_mod = modificar_html(cod_verif)
    html_output_path = os.path.join(OUTPUT_FOLDER, f"{cod_verif}.html")
    with open(html_output_path, 'w', encoding='utf-8') as f:
        f.write(html_mod)

    return render_template("resultado.html", codigo=cod_verif)


def extraer_codigo_verificacion(text):
    for line in text.split("\n"):
        if "Código de Verificación" in line:
            parts = line.split(":")
            if len(parts) == 2:
                return parts[1].strip()
    return None

def modificar_html(codigo):
    soup = BeautifulSoup(HTML_TEMPLATE, 'html.parser')
    botones = soup.find_all('a', href=True)
    for boton in botones:
        if 'verguiapdf/?type=general' in boton['href']:
            boton['href'] = f"/guias/{codigo}.pdf"
    return str(soup)

@app.route('/descargar/<codigo>')
def descargar_pdf(codigo):
    path = os.path.join(OUTPUT_FOLDER, f"{codigo}.pdf")
    print("Ruta=",path)
    return send_file(path, as_attachment=True)

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

def extraer_campos(texto, qr):
    campos = []  # Lista de tuplas (clave, valor)
    lineas = texto.split("\n")
    clave_actual = None
    valor_actual = []
    firmante = ""
    ocurrencias = {}  # Para contar claves repetidas

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
            continue

        if "Firmado:" in linea and i > 0:
            firmante = lineas[i - 1].strip()

        if ":" in linea:
            if clave_actual:
                clave_final = clave_actual.strip()
                ocurrencias[clave_final] = ocurrencias.get(clave_final, 0)
                if ocurrencias[clave_final] > 0:
                    clave_final += str(ocurrencias[clave_final])
                campos.append((clave_final, " ".join(valor_actual).strip()))
                ocurrencias[clave_actual.strip()] += 1

            clave_actual, valor = linea.split(":", 1)

            if clave_actual.strip() == "Precintos instalados":
                clave_final = clave_actual.strip()
                ocurrencias[clave_final] = ocurrencias.get(clave_final, 0)
                if ocurrencias[clave_final] > 0:
                    clave_final += str(ocurrencias[clave_final])
                campos.append((clave_final, valor.strip()))
                ocurrencias[clave_actual.strip()] += 1
                clave_actual = None
                valor_actual = []
            else:
                valor_actual = [valor.strip()]
                ocurrencias.setdefault(clave_actual.strip(), 0)
        elif clave_actual:
            valor_actual.append(linea.strip())

    if clave_actual:
        clave_final = clave_actual.strip()
        ocurrencias[clave_final] = ocurrencias.get(clave_final, 0)
        if ocurrencias[clave_final] > 0:
            clave_final += str(ocurrencias[clave_final])
        campos.append((clave_final, " ".join(valor_actual).strip()))
        ocurrencias[clave_actual.strip()] += 1

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

def dividir_valor_por_ancho_avanzado(c, texto, fuente, tamaño, max_widths):
    """
    Divide el texto en líneas sin cortar palabras, respetando un ancho diferente por línea.
    max_widths puede ser un entero (ancho fijo) o una lista de anchos por línea.
    """
    palabras = texto.split()
    lineas = []
    linea_actual = ""
    linea_index = 0

    while palabras:
        palabra = palabras.pop(0)
        prueba = f"{linea_actual} {palabra}".strip()

        ancho_actual = max_widths if isinstance(max_widths, (int, float)) else \
                       (max_widths[linea_index] if linea_index < len(max_widths) else max_widths[-1])

        if c.stringWidth(prueba, fuente, tamaño) <= ancho_actual:
            linea_actual = prueba
        else:
            if linea_actual:
                lineas.append(linea_actual)
                linea_index += 1
            linea_actual = palabra
    if linea_actual:
        lineas.append(linea_actual)

    return lineas

def draw_parrafo(c, label, valor, x, y, max_width=240, alto_linea=13):
    # Fuentes y tamaños
    font_label = "Helvetica-Bold"
    font_valor = "Helvetica"
    size = 9

    label_text = f"{label}:"
    label_width = c.stringWidth(label_text + " ", font_label, size)

    # Lista de anchos: primera línea con espacio restante, luego el total
    max_widths = [max_width - label_width, max_width]

    # Dividir el valor respetando anchos variables por línea
    lineas_valor = dividir_valor_por_ancho_avanzado(c, valor, font_valor, size, max_widths)

    # Primera línea: label en negrita + primera parte del valor
    c.setFont(font_label, size)
    c.drawString(x, y, label_text)

    c.setFont(font_valor, size)
    c.drawString(x + label_width, y, lineas_valor[0])
    y -= alto_linea

    # Siguientes líneas: solo el valor, alineadas al borde izquierdo
    for linea in lineas_valor[1:]:
        c.drawString(x, y, linea)
        y -= alto_linea

    return y

def insertar_logo_proporcional_ancho(c, ruta_logo, x, y, ancho):
    """
    Inserta el logo ajustando el ancho dado y calculando automáticamente el alto
    para mantener la proporción original.
    """
    if not ruta_logo or not os.path.exists(ruta_logo):
        print(f"[Logo] Ruta inválida o no existe: {ruta_logo}")
        return

    try:
        logo = ImageReader(ruta_logo)
        # Obtener tamaño original de la imagen
        original_ancho, original_alto = logo.getSize()

        # Calcular alto proporcional al nuevo ancho
        escala = ancho / original_ancho
        alto = original_alto * escala

        # Dibujar imagen manteniendo proporción
        c.drawImage(logo, x, y, width=ancho, height=alto, preserveAspectRatio=True, mask='auto')
        print(f"[Logo] Logo insertado proporcionalmente con ancho {ancho} y alto {alto:.2f}.")
    except Exception as e:
        print(f"[Logo] Error al insertar logo: {e}")


def insertar_qr_en_overlay(c, url, x, y, size=150):
    # Generar QR como imagen PNG en memoria (sin bordes)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=0  # Sin borde
    )
    qr.add_data(url)
    qr.make(fit=True)

    img_buffer = BytesIO()
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    # Convertir a objeto que reportlab puede usar
    qr_reader = ImageReader(img_buffer)

    # Dibujar imagen en el PDF
    c.drawImage(qr_reader, x, y, width=size, height=size)

def insertar_firma_completa(c, ruta_firma, firmante, firmado, vigencia, x, y, ancho=150, alto=50, espacio=5, alto_linea=12):
    """
    Inserta firma + firmante en negrita + Firmado y Vigencia centrados bajo la imagen.
    """
    if not ruta_firma or not os.path.exists(ruta_firma):
        print(f"[Firma] Ruta inválida o no existe: {ruta_firma}")
        return

    try:
        # 1. Insertar imagen de firma
        firma = ImageReader(ruta_firma)
        c.drawImage(firma, x, y, width=ancho, height=alto, mask='auto')

        centro_x = x + ancho / 2
        y_texto = y - espacio - 10

        # 2. Firmante (negrita, centrado)
        c.setFont("Helvetica-Bold", 12)
        ancho_firmante = c.stringWidth(firmante, "Helvetica-Bold", 12)
        c.drawString(centro_x - ancho_firmante / 2, y_texto, firmante)
        y_texto -= alto_linea

        # 3. Campo "Firmado: ..."
        firmado_texto = f"Firmado: {firmado}"
        c.setFont("Helvetica", 8)
        ancho_firmado = c.stringWidth(firmado_texto, "Helvetica", 8)
        c.drawString(centro_x - ancho_firmado / 2, y_texto, firmado_texto)
        y_texto -= alto_linea

        # 4. Campo "Vigencia: ..."
        vigencia_texto = f"Vigencia: {vigencia}"
        ancho_vigencia = c.stringWidth(vigencia_texto, "Helvetica", 8)
        c.drawString(centro_x - ancho_vigencia / 2, y_texto, vigencia_texto)

        print("[Firma] Firma y metadatos insertados correctamente.")
    except Exception as e:
        print(f"[Firma] Error insertando firma: {e}")

def generar_overlay_sobre_plantilla(json_path, plantilla_path, salida_path="resultado_final.pdf"):
    # Leer campos
    with open(json_path, "r", encoding="utf-8") as f:
        campos = dict(json.load(f))

    # Leer plantilla y obtener tamaño
    reader = PdfReader(plantilla_path)
    page = reader.pages[0]
    ancho, alto = float(page.mediabox.width), float(page.mediabox.height)

    # Crear overlay en memoria
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(ancho, alto))
    c.setFont("Helvetica", 10)

    # Logo
    insertar_logo_proporcional_ancho(c, ruta_logo=campos.get("logo", ""), x=450, y=770, ancho=120)

    # Informacion General 
    x = 35
    y = alto - 156
    y = draw_parrafo(c, "Número de guía", campos.get('Número de guía', ''), x, y)
    y = draw_parrafo(c, "Número de Factura", campos.get('Número de Factura', ''), x, y)
    y = draw_parrafo(c, "Código de Verificación", campos.get('Código de Verificación', ''),x, y)
    y = draw_parrafo(c, "Fecha y hora de salida", campos.get('Fecha y hora de salida', ''), x, y)
    y = draw_parrafo(c, "Vigencia", campos.get('Vigencia', ''), x, y)
    y = draw_parrafo(c, "Origen", campos.get('Origen', ''), x, y)
    y = draw_parrafo(c, "Destino", campos.get('Destino', ''), x, y)
    y = draw_parrafo(c, "Nombre del conductor", campos.get('Nombre del conductor', ''), x, y)
    y = draw_parrafo(c, "Placa cabezote", campos.get('Placa cabezote', ''), x, y)
    y = draw_parrafo(c, "Placa remolque", campos.get('Placa remolque', ''), x, y)
    y = draw_parrafo(c, "Tipo vehículo", campos.get('Tipo vehículo', ''), x, y)
    y = draw_parrafo(c, "Zona de frontera", campos.get('Zona de frontera', ''), x, y)

    # Codigo QR
    insertar_qr_en_overlay(c, campos.get("codigo_qr", ""), x=100, y=410, size=100)

    # Información de Productos
    y = alto - 560
    y = draw_parrafo(c, "Nombre del producto", campos.get('Nombre del producto', ''), x, y)
    y = draw_parrafo(c, "Cantidad", campos.get('Cantidad', ''), x, y)
    y = draw_parrafo(c, "Código producto", campos.get('Código producto', ''), x, y)
    if campos.get('Nombre del producto1',''):
        y = y - 10
        y = draw_parrafo(c, "Nombre del producto", campos.get('Nombre del producto1', ''), x, y)
        y = draw_parrafo(c, "Cantidad", campos.get('Cantidad1', ''), x, y)
        y = draw_parrafo(c, "Código producto", campos.get('Código producto1', ''), x, y)

    # OBSERVACIONES
    font = "Helvetica-Bold"
    size = 10
    c.setFont(font, size)
    y = 163
    c.drawString(x, y, "OBSERVACIONES")

    # INFORMACIÓN AGENTE DE LA CADENA VENDEDOR
    font = "Helvetica-Bold"
    size = 10
    c.setFont(font, size)
    y = alto - 160
    x = 317
    Ancho2 = 240
    c.drawString(x, y, "INFORMACIÓN AGENTE DE LA CADENA")
    y -= 13
    c.drawString(x, y, "VENDEDOR")
    y -= 20
    y = draw_parrafo(c, "Agente de la cadena vendedor", campos.get('Agente de la cadena vendedor', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Código SICOM", campos.get('Código SICOM', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Planta o despacho", campos.get('Planta o despacho', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Nit", campos.get('Nit', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Departamento de la planta", campos.get('Departamento de la planta', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Municipio planta o despacho", campos.get('Municipio planta o despacho', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Código de la planta", campos.get('Código de la planta', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Número de pedido", campos.get('Número de pedido', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Número OP", campos.get('Número OP', ''), x, y, 240+317)
    y = draw_parrafo(c, "Código divipola agente de la cadena", campos.get('Código divipola agente de la cadena', ''), x, y, Ancho2)
    
    # INFORMACIÓN AGENTE DE LA CADENA COMPRADOR
    font = "Helvetica-Bold"
    size = 10
    c.setFont(font, size)
    y = 490
    x = 317
    c.drawString(x, y, "INFORMACIÓN AGENTE DE LA CADENA")
    y -= 13
    c.drawString(x, y, "COMPRADOR")
    y -= 20
    y = draw_parrafo(c, "Código SICOM1", campos.get('Código SICOM1', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Agente de la cadena del comprador", campos.get('Agente de la cadena del comprador', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Identificacion - NIT", campos.get('Identificacion - NIT', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Departamento solicitante", campos.get('Departamento solicitante', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Municipio solicitante", campos.get('Municipio solicitante', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Dirección", campos.get('Dirección', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Email", campos.get('Email', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Código divipola agente de la cadena", campos.get('Código divipola agente de la cadena1', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Volumen máximo", campos.get('Volumen máximo', ''), x, y, Ancho2)

    # INFORMACIÓN TRANSPORTE
    font = "Helvetica-Bold"
    size = 10
    c.setFont(font, size)
    y = 300
    x = 317
    c.drawString(x, y, "INFORMACIÓN TRANSPORTE")
    y -= 20
    y = draw_parrafo(c, "Transporte a utilizar", campos.get('Transporte a utilizar', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Nombre del conductor", campos.get('Nombre del conductor1', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Número de cédula", campos.get('Número de cédula', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Número de celular", campos.get('Número de celular', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Correo electrónico", campos.get('Correo electrónico', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Placa cabezote", campos.get('Placa cabezote1', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Placa remolque", campos.get('Placa remolque1', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Tipo vehículo", campos.get('Tipo vehículo1', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Manifiesto de carga", campos.get('Manifiesto de carga', ''), x, y, Ancho2)
    y = draw_parrafo(c, "Precintos instalados", campos.get('Precintos instalados', ''), x, y, Ancho2)
    #y = draw_parrafo(c, "Nit", campos.get('Nit', ''), x, y, 240+317)

    c.save()
    buffer.seek(0)

    # Fusionar overlay con plantilla
    overlay_pdf = PdfReader(buffer)
    writer = PdfWriter()
    page.merge_page(overlay_pdf.pages[0])
    writer.add_page(page)

    # Pagina 2 
    page2 = reader.pages[1]
    ancho, alto = float(page2.mediabox.width), float(page2.mediabox.height)
    # Crear overlay en memoria
    buffer2 = BytesIO()
    c2 = canvas.Canvas(buffer2, pagesize=(ancho, alto))
    c2.setFont("Helvetica", 10)

    x = 35
    y = alto - 156

    # Firma
    insertar_firma_completa(c2, ruta_firma=campos.get("img_firma", ""), firmante=campos.get("firmante", ""),
                            firmado=campos.get("Firmado", ""), vigencia=campos.get("Vigencia1", ""),
                            x=365, y=alto-60, ancho=150, alto=50)

    c2.save()
    buffer2.seek(0)

    # Fusionar overlay con plantilla
    overlay2_pdf = PdfReader(buffer2)
    #writer = PdfWriter()
    page2.merge_page(overlay2_pdf.pages[0])
    writer.add_page(page2)


    with open(salida_path, "wb") as f:
        writer.write(f)

    print(f"PDF generado: {salida_path}")

def generar_overlay_sobre_plantilla_reducida(json_path, plantilla_path, salida_path="resultado_final.pdf"):
    # Leer campos
    with open(json_path, "r", encoding="utf-8") as f:
        campos = dict(json.load(f))

    # Leer plantilla y obtener tamaño
    reader = PdfReader(plantilla_path)
    page = reader.pages[0]
    ancho, alto = float(page.mediabox.width), float(page.mediabox.height)

    # Crear overlay en memoria
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(ancho, alto))
    c.setFont("Helvetica", 10)

    # Logo
    insertar_logo_proporcional_ancho(c, ruta_logo=campos.get("logo", ""), x=450, y=770, ancho=120)

    # Informacion General 
    x = 35
    y = alto - 156
    y = draw_parrafo(c, "Número de guía", campos.get('Número de guía', ''), x, y)
    y = draw_parrafo(c, "Número de Factura", campos.get('Número de Factura', ''), x, y)
    y = draw_parrafo(c, "Código de Verificación", campos.get('Código de Verificación', ''),x, y)
    y = draw_parrafo(c, "Fecha y hora de salida", campos.get('Fecha y hora de salida', ''), x, y)
    y = draw_parrafo(c, "Vigencia", campos.get('Vigencia', ''), x, y)
    y = draw_parrafo(c, "Origen", campos.get('Origen', ''), x, y)
    y = draw_parrafo(c, "Destino", campos.get('Destino', ''), x, y)
    y = draw_parrafo(c, "Nombre del conductor", campos.get('Nombre del conductor', ''), x, y)
    y = draw_parrafo(c, "Placa cabezote", campos.get('Placa cabezote', ''), x, y)
    y = draw_parrafo(c, "Placa remolque", campos.get('Placa remolque', ''), x, y)
    y = draw_parrafo(c, "Tipo vehículo", campos.get('Tipo vehículo', ''), x, y)
    y = draw_parrafo(c, "Zona de frontera", campos.get('Zona de frontera', ''), x, y)

    # Codigo QR
    insertar_qr_en_overlay(c, campos.get("codigo_qr", ""), x=100, y=410, size=100)

    c.save()
    buffer.seek(0)

    # Fusionar overlay con plantilla
    overlay_pdf = PdfReader(buffer)
    writer = PdfWriter()
    page.merge_page(overlay_pdf.pages[0])
    writer.add_page(page)

    with open(salida_path, "wb") as f:
        writer.write(f)

    print(f"PDF generado: {salida_path}")

@app.route("/generar_pdf/<codigo>")
def generar_pdf_plantilla(codigo):
    json_path = f"data/{codigo}.json"
    salida_path = f"outputs/{codigo}_completo.pdf"
    plantilla_path = "plantilla_full.pdf"
    try:
        generar_overlay_sobre_plantilla(json_path, plantilla_path, salida_path)
        return send_file(salida_path, as_attachment=True)
    except Exception as e:
        return f"Error al generar el PDF: {str(e)}", 500

@app.route("/generar_pdf_reducido/<codigo>")
def generar_pdf_plantilla1(codigo):
    json_path = f"data/{codigo}.json"
    salida_path = f"outputs/{codigo}.pdf"
    salida_path_html = f"outputs/{codigo}.html"
    plantilla_path = "plantilla_reducida.pdf"
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
    try:
        generar_overlay_sobre_plantilla_reducida(json_path, plantilla_path, salida_path)
        return send_file(salida_path, as_attachment=True)
    except Exception as e:
        return f"Error al generar el PDF: {str(e)}", 500
    
@app.route("/descargar_html/<codigo>")
def descargar_html(codigo):
    json_path = f"data/{codigo}.json"
    salida_path_html = f"outputs/{codigo}.html"
    try:
        return send_file(salida_path_html, as_attachment=True)
    except Exception as e:
        return f"Error al generar el PDF: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)