import base64
import json
import logging
from typing import Optional
import httpx
from fastapi import APIRouter, HTTPException, File, UploadFile, Form

from ..core.config import settings
from ..schemas.measure import FootMeasurementRequest, FootMeasurementResponse

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

async def analyze_image_with_gemini(
    image_base64: str, 
    mime_type: str, 
    height_cm: Optional[float] = None, 
    weight_kg: Optional[float] = None,
    wearing_socks: bool = False
) -> dict:
    """
    Llama a la API REST de Google Gemini (2.5 Flash) enviando la imagen del pie
    y los datos físicos (estatura/peso) y el indicador de calcetines para estimar.
    """
    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY no configurado en el archivo .env")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={settings.gemini_api_key}"
    
    prompt = (
        "Analiza esta imagen de un pie y estima la talla de calzado estándar (EU/EUR) más probable.\n"
        "Para calibrar la escala física, busca un objeto de referencia estándar en la imagen (como una tarjeta plástica de crédito/identificación o una hoja A4) colocada al lado del pie.\n"
        "Además, utiliza los siguientes datos antropométricos del usuario para validar proporciones:\n"
    )
    if height_cm:
        prompt += f"- Estatura: {height_cm} cm\n"
    if weight_kg:
        prompt += f"- Peso: {weight_kg} kg\n"
    
    # Inyección de la regla de calcetines
    if wearing_socks:
        prompt += (
            "- NOTA CRÍTICA: El usuario lleva CALCETINES/MEDIAS en la foto. Esto incrementa artificialmente el contorno y la longitud. "
            "Reduce tu estimación final de talla EU/EUR restando aproximadamente 4mm a 5mm (equivalente a 0.5 o 1 talla completa de calzado) "
            "con respecto a la silueta del calcetín que ves en la foto para aproximar la talla descalzo real del usuario.\n"
        )
    else:
        prompt += "- NOTA: El usuario está DESCALZO en la foto. Estima la talla directamente en base a la silueta del pie.\n"
        
    prompt += (
        "\nCriterios de Confianza:\n"
        "1. Si encuentras un objeto de referencia claro (como una tarjeta de crédito o una hoja de papel) al lado del pie, realiza la calibración píxel-a-centímetro. Si el pie se ve completo desde arriba, la confianza debe ser de 0.90 a 0.98.\n"
        "2. Si NO hay objeto de referencia (tarjeta o papel) en la imagen pero sí hay foto del pie y estatura/peso, estima basándote en proporciones. La confianza máxima en este caso debe ser de 0.65.\n"
        "3. Si la foto es de mala calidad, no se ve el pie completo (faltan dedos o talón), o no corresponde a un pie, la talla debe ser 'N/A' y la confianza 0.0.\n\n"
        "Devuelve únicamente un objeto JSON con los siguientes campos:\n"
        "- 'shoe_size': la talla estimada en formato string (ej: '42' o 'N/A')\n"
        "- 'confidence': un float entre 0.0 y 1.0 que indique tu seguridad en la estimación\n"
        "- 'brand_advice': una recomendación detallada y personalizada en español para comprar tallas en Nike, Adidas y Converse.\n"
        "Asegúrate de que la respuesta sea estrictamente un JSON válido, sin bloques de código ```json ni texto adicional."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": image_base64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        
        # Extraer el texto de la respuesta
        text_response = data["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text_response.strip())
        return result


def get_mock_prediction(
    seed_string: str, 
    height_cm: Optional[float] = None, 
    weight_kg: Optional[float] = None, 
    wearing_socks: bool = False,
    is_demo_notice: bool = False
) -> FootMeasurementResponse:
    """Genera una predicción aproximada mediante datos estadísticos antropométricos para el Mock."""
    if height_cm:
        base_size = int(height_cm / 4.3)
        if weight_kg and weight_kg > 90:
            base_size += 1
            
        # Restar 1 talla para compensar si lleva calcetines en modo demo
        if wearing_socks:
            base_size -= 1
            
        base_size = max(35, min(46, base_size))
        shoe_size = str(base_size)
    else:
        sizes = ["38", "39", "40", "41", "42", "43", "44"]
        idx = len(seed_string) % len(sizes)
        if wearing_socks:
            idx = max(0, idx - 1)
        shoe_size = sizes[idx]
    
    advices = {
        "35": "Talla 35 estimada. Horma delgada. En marcas deportivas sugerimos pedir media talla más.",
        "36": "Talla 36 estimada. Horma estándar. Nike y Adidas se adaptan bien en tu talla habitual.",
        "37": "Talla 37 estimada. Horma estándar. En Converse se aconseja media talla menos.",
        "38": "Talla 38 estimada. Horma estándar. En Nike sugerimos tu talla usual; en Converse, media talla menos.",
        "39": "Talla 39 estimada. Horma estándar. En Adidas te recomendamos media talla más de lo habitual.",
        "40": "Talla 40 estimada. Horma ligeramente ancha. Se recomienda comprar tu talla exacta en marcas europeas.",
        "41": "Talla 41 estimada. Horma estándar. Nike y Puma se ajustan perfectamente a tu medida habitual.",
        "42": "Talla 42 estimada. Horma estándar. Recomendamos Adidas Ultraboost en tu talla normal o media talla más.",
        "43": "Talla 43 estimada. Horma ligeramente estrecha. En calzado deportivo, prefiere una talla extra para mayor comodidad.",
        "44": "Talla 44 estimada. Horma ancha. Excelente soporte. Nike Air Force 1 se ajustará idealmente en tu talla usual.",
        "45": "Talla 45 estimada. Horma ancha. Se recomienda verificar marcas americanas que ofrecen horma ancha (Wide).",
        "46": "Talla 46 estimada. Horma extra ancha. Prestar especial atención a las tablas de tallas de calzado deportivo."
    }
    
    brand_advice = advices.get(shoe_size, "Horma estándar. Se recomienda comprar tu talla de calzado habitual.")
    if wearing_socks:
        brand_advice = f"[Ajustado por calcetines] {brand_advice}"
    if is_demo_notice:
        brand_advice = f"⚠️ [Modo Demo] GEMINI_API_KEY no configurado en backend/.env. Clave de Google Gemini requerida para IA real. {brand_advice}"
        
    confidence = 0.85 + (len(seed_string) % 11) / 100.0
    return FootMeasurementResponse(
        shoe_size=shoe_size,
        brand_advice=brand_advice,
        confidence=round(confidence, 2),
    )


@router.post("/predict", response_model=FootMeasurementResponse)
async def predict_size(request: FootMeasurementRequest):
    if settings.gemini_api_key and settings.gemini_api_key != "your_gemini_api_key_here":
        try:
            async with httpx.AsyncClient() as client:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                img_response = await client.get(str(request.image_url), headers=headers, timeout=15.0)
                img_response.raise_for_status()
                img_bytes = img_response.content
                mime_type = img_response.headers.get("content-type", "image/jpeg")
            
            image_base64 = base64.b64encode(img_bytes).decode("utf-8")
            result = await analyze_image_with_gemini(
                image_base64, mime_type, request.height_cm, request.weight_kg, request.wearing_socks
            )
            
            return FootMeasurementResponse(
                shoe_size=str(result.get("shoe_size", "N/A")),
                brand_advice=str(result.get("brand_advice", "")),
                confidence=float(result.get("confidence", 0.85)),
            )
        except Exception as exc:
            logger.error(f"Error analizando imagen por URL con Gemini: {exc}")
            return get_mock_prediction(
                str(request.image_url), request.height_cm, request.weight_kg, request.wearing_socks, is_demo_notice=True
            )
    else:
        return get_mock_prediction(
            str(request.image_url), request.height_cm, request.weight_kg, request.wearing_socks, is_demo_notice=True
        )


@router.post("/upload", response_model=FootMeasurementResponse)
async def upload_image(
    file: UploadFile = File(...),
    height_cm: Optional[float] = Form(None),
    weight_kg: Optional[float] = Form(None),
    wearing_socks: bool = Form(False)
):
    file_content = await file.read()
    
    if settings.gemini_api_key and settings.gemini_api_key != "your_gemini_api_key_here":
        try:
            image_base64 = base64.b64encode(file_content).decode("utf-8")
            mime_type = file.content_type or "image/jpeg"
            result = await analyze_image_with_gemini(
                image_base64, mime_type, height_cm, weight_kg, wearing_socks
            )
            
            return FootMeasurementResponse(
                shoe_size=str(result.get("shoe_size", "N/A")),
                brand_advice=str(result.get("brand_advice", "")),
                confidence=float(result.get("confidence", 0.85)),
            )
        except Exception as exc:
            logger.error(f"Error analizando archivo subido con Gemini: {exc}")
            return get_mock_prediction(file.filename, height_cm, weight_kg, wearing_socks, is_demo_notice=True)
    else:
        return get_mock_prediction(file.filename, height_cm, weight_kg, wearing_socks, is_demo_notice=True)
