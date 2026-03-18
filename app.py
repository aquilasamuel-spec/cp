from flask import Flask, render_template, redirect, url_for, request, flash, abort, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, TreasuryEntry
from services.excel_service import get_birthdays_of_month, get_members_data, update_member_data, add_member, delete_member
from services.whatsapp_service import send_whatsapp_message
from functools import wraps
import os
from datetime import datetime
import requests
import threading
from services.scheduler import run_automation

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@app.before_request
def check_daily_birthday_reminder():
    """Verifica e dispara as mensagens de aniversário no WhatsApp uma vez por dia."""
    try:
        if request.endpoint and request.endpoint.startswith('static'):
            return
            
        today_str = datetime.now().strftime('%Y-%m-%d')
        reminder_file = os.path.join(os.getcwd(), 'last_reminder.txt')
        
        last_run = ""
        if os.path.exists(reminder_file):
            with open(reminder_file, 'r') as f:
                last_run = f.read().strip()
                
        if last_run != today_str:
            with open(reminder_file, 'w') as f:
                f.write(today_str)
            print(f"[{datetime.now()}] Iniciando verificação diária de aniversários via thread...")
            threading.Thread(target=run_automation).start()
    except Exception as e:
        print(f"[{datetime.now()}] Erro no check_daily_birthday_reminder: {e}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def roles_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if not current_user.has_role(roles):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Username ou senha incorretos!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    # Tradução de meses
    meses = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    mes_atual = meses[datetime.now().month]
    
    birthdays = get_birthdays_of_month()
    # Ordenar aniversariantes por dia
    def sort_key(x):
        try:
            return int(x.get('Data_Nascimento', '01/01/2000').split('/')[0])
        except:
            return 0
    birthdays.sort(key=sort_key)
    
    members = get_members_data()
    total_membros = len(members)
    
    stats = {
        'total_membros': total_membros,
        'gender_dist': {'Masculino': 0, 'Feminino': 0},
        'faixas_etarias': {
            '12-15': 0,
            '16-18': 0,
            '19-25': 0,
            '26-35': 0,
            '35+': 0
        }
    }
    
    current_year = datetime.now().year
    
    for m in members:
        # Gênero
        genero = m.get('Gênero', '').strip().upper()
        if genero in ['M', 'MASCULINO']:
            stats['gender_dist']['Masculino'] += 1
        elif genero in ['F', 'FEMININO']:
            stats['gender_dist']['Feminino'] += 1
            
        # Idade
        dob_str = m.get('Data_Nascimento')
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, '%d/%m/%Y')
                idade = current_year - dob.year
                if 12 <= idade <= 15: stats['faixas_etarias']['12-15'] += 1
                elif 16 <= idade <= 18: stats['faixas_etarias']['16-18'] += 1
                elif 19 <= idade <= 25: stats['faixas_etarias']['19-25'] += 1
                elif 26 <= idade <= 35: stats['faixas_etarias']['26-35'] += 1
                elif idade > 35: stats['faixas_etarias']['35+'] += 1
            except:
                pass
    
    # Filtrar faixas vazias e calcular representabilidade
    faixas_validas = {k: v for k, v in stats['faixas_etarias'].items() if v > 0}
    stats['faixas_etarias'] = faixas_validas
    
    # Percentuais
    stats['percentuais_idade'] = {k: round((v/total_membros)*100, 1) if total_membros > 0 else 0 for k, v in faixas_validas.items()}
    stats['percentuais_genero'] = {k: round((v/total_membros)*100, 1) if total_membros > 0 else 0 for k, v in stats['gender_dist'].items()}

    return render_template('dashboard.html', birthdays=birthdays, stats=stats, mes_atual=mes_atual)

@app.route('/membros')
@login_required
@roles_required(['master', 'coordenador', 'tesoureiro', 'lider_jovens', 'secretario'])
def members():
    members_list = get_members_data()
    return render_template('members.html', members=members_list)

@app.route('/membros/novo', methods=['POST'])
@login_required
@roles_required(['master', 'secretario'])
def new_member():
    data = {
        'Nome': request.form.get('nome'),
        'Data_Nascimento': request.form.get('nascimento'),
        'Congregação': request.form.get('congregacao'),
        'Telefone': request.form.get('telefone'),
        'Cargo': request.form.get('cargo'),
        'Gênero': request.form.get('sexo', '')
    }
    
    if add_member(data):
        flash('Novo membro cadastrado com sucesso!', 'success')
    else:
        flash('Erro ao cadastrar membro.', 'danger')
        
    return redirect(url_for('members'))

@app.route('/membros/editar', methods=['POST'])
@login_required
@roles_required(['master', 'secretario'])
def edit_member():
    original_name = request.form.get('original_name')
    new_data = {
        'Nome': request.form.get('nome'),
        'Data_Nascimento': request.form.get('nascimento'),
        'Congregação': request.form.get('congregacao'),
        'Telefone': request.form.get('telefone'),
        'Cargo': request.form.get('cargo'),
        'Gênero': request.form.get('sexo', '')
    }
    
    if update_member_data(original_name, new_data):
        flash('Informações do membro atualizadas!', 'success')
    else:
        flash('Erro ao atualizar membro.', 'danger')
        
    return redirect(url_for('members'))

@app.route('/membros/excluir/<path:nome>', methods=['POST'])
@login_required
@roles_required(['master', 'secretario'])
def remove_member(nome):
    if delete_member(nome):
        flash('Membro excluído com sucesso!', 'success')
    else:
        flash('Erro ao excluir membro ou membro não encontrado.', 'danger')
        
    return redirect(url_for('members'))

@app.route('/tesouraria')
@login_required
@roles_required(['master', 'coordenador', 'tesoureiro'])
def treasury():
    entries = TreasuryEntry.query.order_by(TreasuryEntry.date.desc()).all()
    total_entrada = db.session.query(db.func.sum(TreasuryEntry.amount)).filter(TreasuryEntry.type == 'Entrada').scalar() or 0
    total_saida = db.session.query(db.func.sum(TreasuryEntry.amount)).filter(TreasuryEntry.type == 'Saída').scalar() or 0
    saldo = total_entrada - total_saida
    
    return render_template('treasury.html', entries=entries, total_entrada=total_entrada, total_saida=total_saida, saldo=saldo, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/tesouraria/salvar', methods=['POST'])
@login_required
@roles_required(['master', 'tesoureiro'])
def save_treasury():
    try:
        valor = request.form.get('valor').replace(',', '.')
        entry = TreasuryEntry(
            amount=float(valor),
            type=request.form.get('tipo'),
            category=request.form.get('categoria'),
            observation=request.form.get('observacao'),
            created_by=current_user.id,
            date=datetime.strptime(request.form.get('data'), '%Y-%m-%d') if request.form.get('data') else datetime.utcnow()
        )
        db.session.add(entry)
        db.session.commit()
        flash('Lançamento realizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao salvar: {e}', 'danger')
        
    return redirect(url_for('treasury'))

@app.route('/admin/acessos')
@login_required
@roles_required(['master'])
def access_management():
    users = User.query.all()
    return render_template('access_management.html', users=users)

@app.route('/admin/acessos/salvar', methods=['POST'])
@login_required
@roles_required(['master'])
def save_access():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    user_id = request.form.get('user_id')

    if user_id:  # Edit existing user
        user = User.query.get(user_id)
        if user:
            user.role = role
            if password:  # Update password if provided
                user.set_password(password)
            flash(f'Acesso de {username} atualizado!', 'success')
    else:  # Create new user
        if User.query.filter_by(username=username).first():
            flash('Este nome de usuário já existe!', 'danger')
        else:
            new_user = User(username=username, role=role)
            new_user.set_password(password)
            db.session.add(new_user)
            flash(f'Acesso para {username} criado com sucesso!', 'success')
            
    db.session.commit()
    return redirect(url_for('access_management'))

@app.route('/admin/acessos/excluir/<int:id>')
@login_required
@roles_required(['master'])
def delete_access(id):
    user = User.query.get_or_404(id)
    if user.username == 'admin':
        flash('O usuário administrador principal não pode ser excluído!', 'danger')
    elif user.id == current_user.id:
        flash('Você não pode excluir seu próprio acesso!', 'danger')
    else:
        db.session.delete(user)
        db.session.commit()
        flash('Acesso removido com sucesso!', 'success')
    return redirect(url_for('access_management'))

@app.route('/send-whatsapp', methods=['POST'])
@login_required
def send_whatsapp():
    data = request.json
    phone = data.get('phone')
    message = data.get('message')
    
    if not phone or not message:
        return jsonify({'success': False, 'error': 'Telefone ou mensagem ausentes.'}), 400
        
    try:
        # Green API Configuration
        api_url = os.getenv('GREEN_API_URL', 'https://api.green-api.com')
        id_instance = os.getenv('GREEN_API_ID_INSTANCE')
        api_token = os.getenv('GREEN_API_TOKEN_INSTANCE')

        if not id_instance or not api_token:
            return jsonify({'success': False, 'error': 'Configuração da API ausente.'}), 500

        # Formatar número: garantir que tenha 55 e termine com @c.us
        clean_phone = phone.replace('+', '').replace(' ', '')
        if not clean_phone.startswith('55') and len(clean_phone) <= 11:
            clean_phone = '55' + clean_phone
        
        chat_id = f"{clean_phone}@c.us"
        
        # Usar o serviço compartilhado para enviar a imagem estática com a legenda
        template_img_path = os.path.join(os.getcwd(), 'static', 'birthday_template.png')
        
        success, result = send_whatsapp_message(
            phone=phone,
            message=template_img_path,
            is_image=True,
            caption=message
        )

        if success:
            log_msg = f"[{datetime.now()}] WHATSAPP ENVIADO PARA {phone} (ID: {result.get('idMessage', 'N/A')})"
            print(log_msg)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': f"Erro ao enviar: {result}"}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/notificar-aniversariantes', methods=['POST'])
@login_required
def notify_leaders_today():
    from services.scheduler import run_automation
    try:
        success, message = run_automation()
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            user = User(username='admin', role='master')
            user.set_password('admin123')
            db.session.add(user)
            db.session.commit()
    
    app.run(debug=True)
