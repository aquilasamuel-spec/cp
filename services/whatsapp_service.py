import os
import requests
from datetime import datetime

def send_whatsapp_message(phone, message, is_image=False, caption=None):
    """
    Envia uma mensagem de WhatsApp via Green API.
    phone: número do destinatário (com ou sem 55)
    message: texto da mensagem (ou caminho do arquivo se is_image=True)
    is_image: define se é envio de imagem
    caption: legenda se is_image=True
    """
    api_url = os.getenv('GREEN_API_URL', 'https://api.green-api.com')
    id_instance = os.getenv('GREEN_API_ID_INSTANCE')
    api_token = os.getenv('GREEN_API_TOKEN_INSTANCE')

    if not id_instance or not api_token:
        print("Erro: Configuração da Green API ausente.")
        return False, "Configuração da API ausente."

    # Formatar número
    clean_phone = str(phone).replace('+', '').replace(' ', '').replace('.0', '')
    if not clean_phone.startswith('55') and len(clean_phone) <= 11:
        clean_phone = '55' + clean_phone
    
    chat_id = f"{clean_phone}@c.us"

    try:
        if is_image:
            # Enviar Imagem
            url = f"{api_url}/waInstance{id_instance}/sendFileByUpload/{api_token}"
            if not os.path.exists(message):
                return False, f"Arquivo não encontrado: {message}"
                
            with open(message, 'rb') as f:
                files = {'file': (os.path.basename(message), f, 'image/png')}
                payload = {
                    "chatId": chat_id,
                    "caption": caption or ""
                }
                response = requests.post(url, data=payload, files=files, timeout=20)
        else:
            # Enviar Texto
            url = f"{api_url}/waInstance{id_instance}/sendMessage/{api_token}"
            payload = {
                "chatId": chat_id,
                "message": message
            }
            response = requests.post(url, json=payload, timeout=10)

        result = response.json()
        if response.status_code == 200:
            print(f"[{datetime.now()}] WhatsApp enviado para {chat_id}")
            return True, result
        else:
            error_msg = result.get('error', response.text)
            print(f"[{datetime.now()}] Erro Green API: {error_msg}")
            return False, error_msg

    except Exception as e:
        print(f"[{datetime.now()}] Exceção ao enviar WhatsApp: {str(e)}")
        return False, str(e)
