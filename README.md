# WebApp QR PDF Editor

Aplicación web desarrollada en Flask para cargar un PDF, reemplazar su código QR por uno nuevo apuntando a una URL dinámica, y generar una versión reducida del PDF.

## 🚀 Características

- Carga de archivo PDF
- Detección automática del QR original
- Inserción de nuevo QR dinámico
- Generación de PDF reducido (solo primera página sin secciones)
- Página HTML generada con enlace al PDF reducido
- Interfaz responsiva con Bootstrap

## 🛠 Requisitos

- Python 3.10+

## 📦 Instalación local

```bash
git clone https://github.com/tuusuario/webapp_qr_pdf_editor.git
cd webapp_qr_pdf_editor
python -m venv venv
source venv/bin/activate  # o venv\Scripts\activate en Windows
pip install -r requirements.txt
python app.py
```

Abre en el navegador: [http://localhost:5000](http://localhost:5000)

## ☁️ Despliegue en producción

### Heroku

1. Asegúrate de tener `Procfile` y `runtime.txt` como se describe en este paquete
2. Ejecuta:

```bash
heroku login
heroku create nombre-de-tu-app
git init
heroku git:remote -a nombre-de-tu-app
git add .
git commit -m "Deploy"
git push heroku master
```

## 📁 Estructura

Ver sección "Estructura del paquete deployable".
