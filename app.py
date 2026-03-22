from flask import Flask, render_template, redirect, url_for, request, flash, abort, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, TreasuryEntry, Rehearsal, RehearsalAttendance
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

# Configura o diretório persistente de dados, caso exista
DATA_DIR = os.environ.get('DATA_DIR', os.getcwd())
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

# Define o caminho do banco de dados apontando para o Disco Persistente
db_path = os.path.join(DATA_DIR, 'database.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
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
@roles_required(['master', 'coordenador', 'secretario'])
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
@roles_required(['master', 'coordenador', 'secretario'])
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
@roles_required(['master', 'coordenador', 'secretario'])
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
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    
    all_entries = TreasuryEntry.query.order_by(TreasuryEntry.date.desc()).all()
    
    current_year = datetime.now().year
    chart_year = year if year else current_year
    
    if month:
        import calendar
        num_days = calendar.monthrange(chart_year, month)[1]
        chart_labels = [str(d) for d in range(1, num_days + 1)]
        chart_data = {'entradas': [0]*num_days, 'saidas': [0]*num_days}
        
        for e in all_entries:
            if e.date.year == chart_year and e.date.month == month:
                idx = e.date.day - 1
                if e.type == 'Entrada':
                    chart_data['entradas'][idx] += e.amount
                elif e.type == 'Saída':
                    chart_data['saidas'][idx] += e.amount
    else:
        chart_labels = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
        chart_data = {'entradas': [0]*12, 'saidas': [0]*12}
        
        for e in all_entries:
            if e.date.year == chart_year:
                idx = e.date.month - 1
                if e.type == 'Entrada':
                    chart_data['entradas'][idx] += e.amount
                elif e.type == 'Saída':
                    chart_data['saidas'][idx] += e.amount
                
    if month:
        all_entries = [e for e in all_entries if e.date.month == month]
    if year:
        all_entries = [e for e in all_entries if e.date.year == year]
        
    total_entrada = sum(e.amount for e in all_entries if e.type == 'Entrada')
    total_saida = sum(e.amount for e in all_entries if e.type == 'Saída')
    saldo = total_entrada - total_saida
    
    years = range(current_year - 2, current_year + 2)
    
    return render_template('treasury.html', 
                           entries=all_entries, 
                           total_entrada=total_entrada, 
                           total_saida=total_saida, 
                           saldo=saldo, 
                           today=datetime.now().strftime('%Y-%m-%d'),
                           selected_month=month,
                           selected_year=year,
                           chart_year=chart_year,
                           years=years,
                           chart_data=chart_data,
                           chart_labels=chart_labels)

@app.route('/tesouraria/relatorio_geral')
@login_required
@roles_required(['master', 'coordenador', 'tesoureiro'])
def relatorio_geral_tesouraria():
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    
    all_entries = TreasuryEntry.query.order_by(TreasuryEntry.date.asc()).all()
    
    if month:
        all_entries = [e for e in all_entries if e.date.month == month]
    if year:
        all_entries = [e for e in all_entries if e.date.year == year]
        
    total_entrada = sum(e.amount for e in all_entries if e.type == 'Entrada')
    total_saida = sum(e.amount for e in all_entries if e.type == 'Saída')
    saldo = total_entrada - total_saida
    
    meses_dict = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    
    filtro_text = ""
    if month and year:
        filtro_text = f"Filtro aplicado: {meses_dict.get(month, '')} de {year}"
    elif month:
        filtro_text = f"Filtro aplicado: {meses_dict.get(month, '')}"
    elif year:
        filtro_text = f"Filtro aplicado: Ano de {year}"
        
    return render_template('tesouraria_relatorio_geral.html', 
                           entries=all_entries, 
                           total_entrada=total_entrada, 
                           total_saida=total_saida, 
                           saldo=saldo,
                           filtro_text=filtro_text)

@app.route('/tesouraria/salvar', methods=['POST'])
@login_required
@roles_required(['master', 'coordenador', 'tesoureiro'])
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

@app.route('/tesouraria/editar/<int:id>', methods=['POST'])
@login_required
@roles_required(['master', 'coordenador', 'tesoureiro'])
def edit_treasury(id):
    entry = TreasuryEntry.query.get_or_404(id)
    try:
        valor = request.form.get('valor').replace(',', '.')
        entry.amount = float(valor)
        entry.type = request.form.get('tipo')
        entry.category = request.form.get('categoria')
        entry.observation = request.form.get('observacao')
        if request.form.get('data'):
            entry.date = datetime.strptime(request.form.get('data'), '%Y-%m-%d')
        db.session.commit()
        flash('Lançamento atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar: {e}', 'danger')
        
    return redirect(url_for('treasury'))

@app.route('/tesouraria/excluir/<int:id>', methods=['POST'])
@login_required
@roles_required(['master', 'coordenador', 'tesoureiro'])
def delete_treasury(id):
    entry = TreasuryEntry.query.get_or_404(id)
    try:
        db.session.delete(entry)
        db.session.commit()
        flash('Lançamento excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir: {e}', 'danger')
        
    return redirect(url_for('treasury'))

@app.route('/admin/acessos')
@login_required
@roles_required(['master', 'coordenador'])
def access_management():
    users = User.query.all()
    return render_template('access_management.html', users=users)

@app.route('/admin/acessos/salvar', methods=['POST'])
@login_required
@roles_required(['master', 'coordenador'])
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
@roles_required(['master', 'coordenador'])
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

@app.route('/ensaios')
@login_required
@roles_required(['master', 'lider_jovens', 'coordenador', 'secretario'])
def ensaios_list():
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    
    ensaios = Rehearsal.query.order_by(Rehearsal.date.desc()).all()
    
    if month:
        ensaios = [e for e in ensaios if e.date.month == month]
    if year:
        ensaios = [e for e in ensaios if e.date.year == year]
        
    ensaios_data = []
    for ensaio in ensaios:
        presentes = RehearsalAttendance.query.filter_by(rehearsal_id=ensaio.id, is_present=True).count()
        ausentes = RehearsalAttendance.query.filter_by(rehearsal_id=ensaio.id, is_present=False).count()
        ensaios_data.append({
            'ensaio': ensaio,
            'presentes': presentes,
            'ausentes': ausentes
        })
    
    current_year = datetime.now().year
    years = range(current_year - 2, current_year + 2)    
        
    return render_template('ensaios.html', ensaios=ensaios_data, selected_month=month, selected_year=year, years=years)

@app.route('/ensaios/novo', methods=['GET', 'POST'])
@login_required
@roles_required(['master', 'lider_jovens', 'coordenador', 'secretario'])
def new_ensaio():
    members = get_members_data()
    # Ordenar membros
    members = sorted(members, key=lambda x: str(x.get('Nome', '')))
    
    if request.method == 'POST':
        data_str = request.form.get('data')
        try:
            ensaio_date = datetime.strptime(data_str, '%Y-%m-%d').date()
        except:
            flash('Data inválida.', 'danger')
            return redirect(url_for('new_ensaio'))
            
        new_rehearsal = Rehearsal(date=ensaio_date, created_by=current_user.id)
        db.session.add(new_rehearsal)
        db.session.commit()
        
        presentes_nomes = request.form.getlist('presente')
        
        for m in members:
            nome = m.get('Nome', '')
            if not nome: continue
            is_present = nome in presentes_nomes
            att = RehearsalAttendance(rehearsal_id=new_rehearsal.id, member_name=nome, is_present=is_present)
            db.session.add(att)
            
        db.session.commit()
        flash('Ensaio registrado com sucesso!', 'success')
        return redirect(url_for('ensaios_list'))
        
    return render_template('ensaio_form.html', members=members, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/ensaios/<int:id>')
@login_required
@roles_required(['master', 'lider_jovens', 'coordenador', 'secretario'])
def view_ensaio(id):
    ensaio = Rehearsal.query.get_or_404(id)
    attendances = RehearsalAttendance.query.filter_by(rehearsal_id=id).all()
    
    presentes = [a for a in attendances if a.is_present]
    ausentes = [a for a in attendances if not a.is_present]
    
    creator = User.query.get(ensaio.created_by)
    creator_name = creator.username if creator else 'Desconhecido'
    
    return render_template('ensaio_view.html', 
                           ensaio=ensaio, 
                           presentes=presentes, 
                           ausentes=ausentes,
                           creator_name=creator_name)

@app.route('/ensaios/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@roles_required(['master', 'lider_jovens', 'coordenador', 'secretario'])
def edit_ensaio(id):
    ensaio = Rehearsal.query.get_or_404(id)
    members = get_members_data()
    members = sorted(members, key=lambda x: str(x.get('Nome', '')))
    
    if request.method == 'POST':
        data_str = request.form.get('data')
        try:
            ensaio.date = datetime.strptime(data_str, '%Y-%m-%d').date()
        except:
            flash('Data inválida.', 'danger')
            return redirect(url_for('edit_ensaio', id=id))
            
        db.session.commit()
        
        # Limpar chamadas antigas
        RehearsalAttendance.query.filter_by(rehearsal_id=ensaio.id).delete()
        
        presentes_nomes = request.form.getlist('presente')
        
        for m in members:
            nome = m.get('Nome', '')
            if not nome: continue
            is_present = nome in presentes_nomes
            att = RehearsalAttendance(rehearsal_id=ensaio.id, member_name=nome, is_present=is_present)
            db.session.add(att)
            
        db.session.commit()
        flash('Ensaio atualizado com sucesso!', 'success')
        return redirect(url_for('view_ensaio', id=ensaio.id))
        
    old_attendances = RehearsalAttendance.query.filter_by(rehearsal_id=ensaio.id, is_present=True).all()
    presentes_nomes = [a.member_name for a in old_attendances]
    return render_template('ensaio_form.html', members=members, ensaio=ensaio, presentes_nomes=presentes_nomes)

@app.route('/ensaios/<int:id>/excluir', methods=['POST'])
@login_required
@roles_required(['master', 'lider_jovens', 'coordenador', 'secretario'])
def delete_ensaio(id):
    ensaio = Rehearsal.query.get_or_404(id)
    RehearsalAttendance.query.filter_by(rehearsal_id=id).delete()
    db.session.delete(ensaio)
    db.session.commit()
    flash('Ensaio excluído com sucesso!', 'success')
    return redirect(url_for('ensaios_list'))

@app.route('/ensaios/<int:id>/notificar_ausentes', methods=['POST'])
@login_required
@roles_required(['master', 'lider_jovens', 'coordenador'])
def notify_ausentes(id):
    ensaio = Rehearsal.query.get_or_404(id)
    attendances = RehearsalAttendance.query.filter_by(rehearsal_id=id, is_present=False).all()
    ausentes_nomes = [a.member_name for a in attendances]
    
    members = get_members_data()
    enviados = 0
    
    ensaio_data_str = ensaio.date.strftime('%d/%m/%Y')
    mensagem = f"A Paz do Senhor! Sentimos a sua falta no ensaio de {ensaio_data_str}. Você é muito importante para nós! Esperamos te ver no próximo! 🙌"
    
    for m in members:
        if m.get('Nome') in ausentes_nomes and m.get('Telefone'):
            phone = str(m['Telefone'])
            success, _ = send_whatsapp_message(phone=phone, message=mensagem, is_image=False)
            if success: enviados += 1
            
    flash(f'Mensagens enviadas para {enviados} ausentes!', 'success')
    return redirect(url_for('view_ensaio', id=id))

@app.route('/ensaios/<int:id>/notificar_presentes', methods=['POST'])
@login_required
@roles_required(['master', 'lider_jovens', 'coordenador'])
def notify_presentes(id):
    ensaio = Rehearsal.query.get_or_404(id)
    attendances = RehearsalAttendance.query.filter_by(rehearsal_id=id, is_present=True).all()
    presentes_nomes = [a.member_name for a in attendances]
    
    members = get_members_data()
    enviados = 0
    
    ensaio_data_str = ensaio.date.strftime('%d/%m/%Y')
    mensagem = f"A Paz do Senhor! Passando para agradecer a Deus pela sua vida e pela sua presença no ensaio de {ensaio_data_str}. Vocês são muito importantes! 🙏"
    
    for m in members:
        if m.get('Nome') in presentes_nomes and m.get('Telefone'):
            phone = str(m['Telefone'])
            success, _ = send_whatsapp_message(phone=phone, message=mensagem, is_image=False)
            if success: enviados += 1
            
    flash(f'Mensagens enviadas para {enviados} presentes!', 'success')
    return redirect(url_for('view_ensaio', id=id))

@app.route('/ensaios/relatorio_geral')
@login_required
@roles_required(['master', 'lider_jovens', 'coordenador', 'secretario'])
def relatorio_geral_ensaios():
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    
    ensaios = Rehearsal.query.order_by(Rehearsal.date.asc()).all()
    
    if month:
        ensaios = [e for e in ensaios if e.date.month == month]
    if year:
        ensaios = [e for e in ensaios if e.date.year == year]
        
    ensaio_ids = [e.id for e in ensaios]
    if not ensaio_ids:
        attendances = []
    else:
        attendances = RehearsalAttendance.query.filter(RehearsalAttendance.rehearsal_id.in_(ensaio_ids)).all()
    
    members_data = {}
    total_presencas = 0
    total_ausencias = 0
    
    for att in attendances:
        if att.member_name not in members_data:
            members_data[att.member_name] = {}
        members_data[att.member_name][att.rehearsal_id] = att.is_present
        if att.is_present:
            total_presencas += 1
        else:
            total_ausencias += 1
            
    total_ensaios = len(ensaios)
    total_marcacoes = total_presencas + total_ausencias
    taxa_presenca = (total_presencas / total_marcacoes * 100) if total_marcacoes > 0 else 0
    
    active_membros = get_members_data()
    active_names = [m.get('Nome') for m in active_membros if m.get('Nome')]
    
    all_names = set(list(members_data.keys()) + active_names)
    members_list = []
    
    for name in sorted(list(all_names)):
        presences_for_member = members_data.get(name, {})
        row = {'nome': name, 'presencas': 0, 'faltas': 0, 'marcacoes': {}}
        for e in ensaios:
            if e.id in presences_for_member:
                is_p = presences_for_member[e.id]
                row['marcacoes'][e.id] = "V" if is_p else "X"
                if is_p: row['presencas'] += 1
                else: row['faltas'] += 1
            else:
                row['marcacoes'][e.id] = "-"
        members_list.append(row)

    meses_dict = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    
    filtro_text = ""
    if month and year:
        filtro_text = f"Filtro aplicado: {meses_dict.get(month, '')} de {year}"
    elif month:
        filtro_text = f"Filtro aplicado: {meses_dict.get(month, '')}"
    elif year:
        filtro_text = f"Filtro aplicado: Ano de {year}"
        
    return render_template('ensaio_relatorio_geral.html', 
                           ensaios=ensaios, 
                           members=members_list, 
                           total_ensaios=total_ensaios,
                           total_presencas=total_presencas,
                           total_ausencias=total_ausencias,
                           taxa_presenca=round(taxa_presenca, 1),
                           filtro_text=filtro_text)

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

with app.app_context():
    db.create_all()
    # Verifica inicialmente se o admin existe
    if not User.query.filter_by(username='admin').first():
        user = User(username='admin', role='master')
        user.set_password('admin123')
        db.session.add(user)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
