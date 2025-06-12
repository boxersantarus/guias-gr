texto = """
GUIA DIGITAL DE TRANSPORTE DE
COMBUSTIBLES LÍQUIDOS
DERIVADOS DEL PETRÓLEO
INFORMACIÓN
GENERAL
Número de guía: 4501510000066769
Número de Factura: 1400240398
Código de Verificación: WsVVZ3
Fecha y hora de salida: 2025-06-07  01:31:29
Vigencia: 14 Horas
Origen: GALAPA
Destino: SINCELEJO
Nombre del conductor: EMIRO DE JESUS DE LA
HOZ PALACIOS
Placa cabezote: SPH020
Placa remolque: N/A
Tipo vehículo: CARRO TANQUE
Zona de frontera: NO
Para validar la autenticidad de esta guía puede consultar en la
página https://sigdi.sicom.gov.co/guias/consulta/ O por medio
del siguiente código QR
INFORMACIÓN
PRODUCTOS
Nombre del producto:  E10 - GASOLINA MOTOR
CORRIENTE CON 10% DE ALCOHOL CARBURANTE
Cantidad:  5660
Código producto:  48
OBSERVACIONES
INFORMACIÓN
DETALLADA
INFORMACIÓN AGENTE DE LA CADENA
VENDEDOR
Agente de la cadena vendedor: BIOMAX
Código SICOM: 330015
Planta o despacho: PLANTA CONJUNTA GALAPA
Nit: 830136799-1
Departamento de la planta: ATLANTICO
Municipio planta o despacho: GALAPA
Código de la planta: 450151
Número de pedido: 166781000694610
Número OP: OPS-716462
Código divipola agente de la cadena: 08296
INFORMACIÓN AGENTE DE LA CADENA
COMPRADOR
Código SICOM: 635339
Agente de la cadena del comprador: EDS
SUPERESTACION SANTA MONICA
Identificacion - NIT: 900364178-9
Departamento solicitante: SUCRE
Municipio solicitante: SINCELEJO
Dirección: CALLE N° 38 57 1036 INT 1
Email: eds_santamonica@hotmail.com
Código divipola agente de la cadena: 70001
Volumen máximo: NO
INFORMACIÓN TRANSPORTE
Transporte a utilizar: TERRESTRE
Nombre del conductor: EMIRO DE JESUS DE LA
HOZ PALACIOS
Número de cédula: 92558996
Número de celular: 3004477543
Correo electrónico: emiropalacios66@hotmail.com
Placa cabezote: SPH020
Placa remolque: N/A
Tipo vehículo: CARRO TANQUE
Manifiesto de carga: No
Precintos instalados: n/a
VIGENTE

JENNY MARCELA BENAVIDES ORTIZ
Firmado: 07/06/2025 01:31:29
Vigencia: 07/06/2025 15:31:29"""

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

# Uso de la función
qr_url = "https://www.sicom.gov.co"
campos = extraer_campos(texto, qr_url)

# Visualización de los resultados
for clave, valor in campos:
    print(f"{clave}: {valor}")


