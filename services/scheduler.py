import sys
import os
from datetime import datetime

# Adicionar o diretório raiz ao path para importar services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.excel_service import get_birthdays_of_day, get_members_data
from services.whatsapp_service import send_whatsapp_message

def generate_html_message(member):
    return f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 500px; margin: 20px auto; border-radius: 20px; overflow: hidden; box-shadow: 0 15px 35px rgba(0,0,0,0.2); background-color: #ffffff;">
        <div style="background: linear-gradient(135deg, #001f3f 0%, #004080 100%); padding: 40px 20px; text-align: center; color: #ffffff;">
            <div style="display: inline-block; padding: 10px; border: 2px solid #ffd700; border-radius: 50%; margin-bottom: 20px;">
                <span style="font-size: 40px;">🎂</span>
            </div>
            <h1 style="margin: 0; font-size: 28px; letter-spacing: 1px; text-transform: uppercase; color: #ffd700;">Feliz Aniversário!</h1>
            <p style="margin-top: 10px; opacity: 0.9; font-style: italic;">Cantico Pentecostal</p>
        </div>
        <div style="padding: 40px 30px; text-align: center;">
            <h2 style="color: #001f3f; margin-bottom: 10px; font-size: 24px;">{member.get('Nome')}</h2>
            <p style="color: #555; line-height: 1.6; font-size: 16px;">
                Hoje celebramos com alegria a sua vida! Que a graça do Senhor transborde sobre você e seu ministério.
            </p>
            <div style="border-top: 2px solid #f0f0f0; border-bottom: 2px solid #f0f0f0; padding: 20px 0; margin: 30px 0;">
                <div style="display: flex; justify-content: center; gap: 20px; font-size: 14px; color: #777;">
                    <div><strong>FUNÇÃO:</strong><br><span style="color: #004080;">{member.get('Cargo')}</span></div>
                    <div style="width: 1px; background: #eee;"></div>
                    <div><strong>CONGREGAÇÃO:</strong><br><span style="color: #004080;">{member.get('Congregação')}</span></div>
                </div>
            </div>
            <p style="color: #c5a059; font-weight: 600; font-size: 14px; margin: 0;">
                "O Senhor te abençoe e te guarde..." <br> Números 6:24
            </p>
        </div>
        <div style="background: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #eee;">
            <p style="margin: 0; color: #bbb; font-size: 10px; text-transform: uppercase; letter-spacing: 2px;">
                © 2026 UJAD - Cantico Pentecostal
            </p>
        </div>
    </div>
    """
def run_automation():
    print(f"[{datetime.now()}] Iniciando verificação de aniversariantes...")
    today_birthdays = get_birthdays_of_day()
    
    if not today_birthdays:
        msg = "Nenhum aniversariante hoje."
        print(msg)
        return False, msg

    # 1. Identificar Líderes
    leader_phones = []
    
    # Do .env
    env_leader = os.getenv('LEADER_PHONE')
    if env_leader:
        leader_phones.append(env_leader)
        
    # Do Excel
    members = get_members_data()
    for m in members:
        if m.get('Cargo') == 'LIDER' and m.get('Telefone'):
            leader_phones.append(m.get('Telefone'))
    
    # Remover duplicatas
    leader_phones = list(set(leader_phones))
    
    if not leader_phones:
        msg = "Aviso: Nenhum líder encontrado para receber a notificação."
        print(msg)
        return False, msg

    # 2. Formatar mensagem para os líderes
    birthday_names = [m.get('Nome') for m in today_birthdays]
    
    if len(birthday_names) == 1:
        text = f"📢 *Lembrete de Aniversário*\n\nOlá Líder! Passando para lembrar que hoje temos um aniversariante no Cantico Pentecostal:\n\n🎂 *{birthday_names[0]}*\n\nNão esqueça de enviar os parabéns! 🎉"
    else:
        names_list = "\n- " + "\n- ".join(birthday_names)
        text = f"📢 *Lembrete de Aniversário*\n\nOlá Líder! Passando para lembrar que hoje temos {len(birthday_names)} aniversariantes no Cantico Pentecostal:{names_list}\n\nNão esqueça de enviar os parabéns! 🎉"

    # 3. Enviar para cada líder
    success_count = 0
    errors = []
    for leader_phone in leader_phones:
        success, result = send_whatsapp_message(leader_phone, text)
        if success:
            print(f"Notificação enviada com sucesso para o líder {leader_phone}")
            success_count += 1
        else:
            print(f"Falha ao enviar notificação para o líder {leader_phone}: {result}")
            errors.append(f"{leader_phone}: {result}")
            
    if success_count > 0:
        return True, f"Notificações enviadas com sucesso para {success_count} líder(es)!"
    else:
        return False, f"Falha ao enviar notificações: {', '.join(errors)}"

if __name__ == "__main__":
    run_automation()
