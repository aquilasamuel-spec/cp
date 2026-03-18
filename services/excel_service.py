import pandas as pd
import os
from datetime import datetime

# Fontes de dados
PRIMARY_FILE = 'CADASTRAMENTO_CP.xlsx'
ACTIVE_FILE = 'MEMBROS_ATIVOS.xlsx'

def get_best_col(df, standard_name):
    """Encontra o melhor nome de coluna no DataFrame para um nome padrão."""
    if standard_name in df.columns:
        return standard_name
    for c in df.columns:
        if c.upper() == standard_name.upper():
            return c
    return standard_name

def clean_phone(val):
    """Remove o .0 e normaliza o telefone como string."""
    if pd.isna(val) or val == "":
        return ""
    val_str = str(val).strip()
    if val_str.endswith('.0'):
        val_str = val_str[:-2]
    return val_str

def get_members_data():
    """Lê os dados dos membros, priorizando o arquivo de dados ativos e complementando com o primário."""
    base_path = os.getcwd()
    primary_path = os.path.join(base_path, PRIMARY_FILE)
    active_path = os.path.join(base_path, ACTIVE_FILE)
    
    df_active = None
    if os.path.exists(active_path):
        try:
            df_active = pd.read_excel(active_path)
            # Normaliza nomes de colunas para facilitar o merge interno
            df_active.columns = [c.upper() for c in df_active.columns]
        except Exception as e:
            print(f"Erro ao ler arquivo ativo: {e}")

    df_primary = None
    if os.path.exists(primary_path):
        try:
            df_primary = pd.read_excel(primary_path)
            df_primary.columns = [c.upper() for c in df_primary.columns]
        except Exception as e:
            print(f"Erro ao ler arquivo primário: {e}")

    # Se não houver nenhum arquivo, retorna vazio
    if df_active is None and df_primary is None:
        return []

    # Se o arquivo ativo não existir, inicializa-o a partir do primário
    if df_active is None:
        df_merged = df_primary.copy()
    else:
        if df_primary is not None:
            # Merge: Mantém dados do Active, adiciona novos do Primary que não estão no Active
            # Identificadores: NOME (considerando nomes únicos para simplificar)
            df_primary['NOME_TMP'] = df_primary['NOME'].astype(str).str.strip().str.upper()
            df_active['NOME_TMP'] = df_active['NOME'].astype(str).str.strip().str.upper()
            
            # Membros que estão no primário mas não no ativo
            new_members = df_primary[~df_primary['NOME_TMP'].isin(df_active['NOME_TMP'])]
            
            if not new_members.empty:
                df_merged = pd.concat([df_active, new_members], ignore_index=True)
            else:
                df_merged = df_active
        else:
            df_merged = df_active

    # Garante colunas essenciais
    for col in ['NOME', 'DATA DE NASCIMENTO', 'SEXO', 'CIDADE', 'FUNÇÃO', 'TELEFONE']:
        if col not in df_merged.columns:
            df_merged[col] = ""

    members = []
    for _, row in df_merged.iterrows():
        # Normalização de Gênero
        raw_gender = str(row.get("SEXO", "")).strip().upper()
        if raw_gender.startswith('F'):
            gender = "Feminino"
        elif raw_gender.startswith('M'):
            gender = "Masculino"
        else:
            gender = ""
        
        member = {
            "Nome": str(row.get("NOME", "")).strip().upper(),
            "Telefone": clean_phone(row.get("TELEFONE", "")),
            "Cargo": str(row.get("FUNÇÃO", "COMPONENTE")),
            "Congregação": str(row.get("CIDADE", "CP")),
            "Gênero": gender,
        }
        
        # Tratamento da Data de Nascimento
        dob = row.get("DATA DE NASCIMENTO")
        if isinstance(dob, (pd.Timestamp, datetime)):
            member["Data_Nascimento"] = dob.strftime('%d/%m/%Y')
        elif pd.isna(dob):
            member["Data_Nascimento"] = ""
        else:
            member["Data_Nascimento"] = str(dob)
        
        # Limpeza de strings que podem ser "nan"
        for key in member:
            if member[key] == "nan":
                member[key] = ""
                
        members.append(member)
                
    return members

def save_active_data(df):
    """Garante que as colunas corretas sejam salvas no arquivo ativo."""
    cols = ['NOME', 'DATA DE NASCIMENTO', 'SEXO', 'CIDADE', 'FUNÇÃO', 'TELEFONE']
    # Mantém apenas as colunas desejadas que existirem no DF
    df_to_save = df[[c for c in cols if c in df.columns]].copy()
    # Adiciona as que faltarem
    for c in cols:
        if c not in df_to_save.columns:
            df_to_save[c] = ""
    
    df_to_save.to_excel(ACTIVE_FILE, index=False)

def add_member(data):
    """Adiciona um novo membro EXCLUSIVAMENTE ao arquivo ativo."""
    try:
        if os.path.exists(ACTIVE_FILE):
            df = pd.read_excel(ACTIVE_FILE)
            df.columns = [c.upper() for c in df.columns]
        else:
            # Se não existir, tenta carregar do primário para inicializar
            members = get_members_data()
            df = pd.DataFrame([ {c.upper(): m.get(c.capitalize(), "") for c in ['NOME', 'DATA DE NASCIMENTO', 'SEXO', 'CIDADE', 'FUNÇÃO', 'TELEFONE']} for m in members])

        new_row = {
            'NOME': data.get('Nome'),
            'DATA DE NASCIMENTO': data.get('Data_Nascimento'),
            'FUNÇÃO': data.get('Cargo'),
            'CIDADE': data.get('Congregação'),
            'TELEFONE': clean_phone(data.get('Telefone')),
            'SEXO': data.get('Gênero', '')
        }
        
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_active_data(df)
        return True
    except Exception as e:
        print(f"Erro ao adicionar membro: {e}")
        return False

def update_member_data(member_name, new_data):
    """Atualiza as informações de um membro especificamente no arquivo ativo."""
    try:
        # Carrega os dados mesclados para garantir que temos o membro (mesmo que venha do primário)
        all_members = get_members_data()
        df = pd.DataFrame([ {
            'NOME': m['Nome'],
            'DATA DE NASCIMENTO': m['Data_Nascimento'],
            'SEXO': m['Gênero'],
            'CIDADE': m['Congregação'],
            'FUNÇÃO': m['Cargo'],
            'TELEFONE': m['Telefone']
        } for m in all_members])

        # Localiza a linha
        df['NOME_TMP'] = df['NOME'].astype(str).str.strip().str.upper()
        target_name = str(member_name).strip().upper()
        mask = df['NOME_TMP'] == target_name
        
        if not mask.any():
            return False
            
        # Mapeia as chaves de volta
        if 'Nome' in new_data: df.loc[mask, 'NOME'] = new_data['Nome']
        if 'Data_Nascimento' in new_data: df.loc[mask, 'DATA DE NASCIMENTO'] = new_data['Data_Nascimento']
        if 'Congregação' in new_data: df.loc[mask, 'CIDADE'] = new_data['Congregação']
        if 'Cargo' in new_data: df.loc[mask, 'FUNÇÃO'] = new_data['Cargo']
        if 'Telefone' in new_data: df.loc[mask, 'TELEFONE'] = clean_phone(new_data['Telefone'])
        if 'Gênero' in new_data: df.loc[mask, 'SEXO'] = new_data['Gênero']

        # Remove coluna temporária e salva
        df = df.drop(columns=['NOME_TMP'])
        save_active_data(df)
        return True
    except Exception as e:
        print(f"Erro ao atualizar membro: {e}")
        return False

def delete_member(member_name):
    """Remove um membro do arquivo ativo."""
    try:
        if os.path.exists(ACTIVE_FILE):
            df = pd.read_excel(ACTIVE_FILE)
            df.columns = [c.upper() for c in df.columns]
        else:
            members = get_members_data()
            df = pd.DataFrame([ {c.upper(): m.get(c.capitalize(), "") for c in ['NOME', 'DATA DE NASCIMENTO', 'SEXO', 'CIDADE', 'FUNÇÃO', 'TELEFONE']} for m in members])
        
        df['NOME_TMP'] = df['NOME'].astype(str).str.strip().str.upper()
        target_name = str(member_name).strip().upper()
        mask = df['NOME_TMP'] == target_name
        
        if not mask.any():
            return False
            
        # Filtra removendo a linha encontrada
        df = df[~mask]
        
        # Remove coluna temporária e salva
        df = df.drop(columns=['NOME_TMP'])
        save_active_data(df)
        return True
    except Exception as e:
        print(f"Erro ao excluir membro: {e}")
        return False

def get_birthdays_of_month(month=None):
    """Retorna os aniversariantes do mês especificado."""
    if month is None:
        month = datetime.now().month
    
    all_members = get_members_data()
    birthdays = []
    
    for member in all_members:
        dob_str = member.get('Data_Nascimento')
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, '%d/%m/%Y')
                if dob.month == month:
                    birthdays.append(member)
            except ValueError:
                continue
    
    # Ordenar por dia
    birthdays.sort(key=lambda x: int(x['Data_Nascimento'].split('/')[0]) if '/' in x['Data_Nascimento'] else 0)
    return birthdays

def get_birthdays_of_day(day=None, month=None):
    """Retorna os aniversariantes do dia especificado."""
    now = datetime.now()
    if day is None: day = now.day
    if month is None: month = now.month
    
    all_members = get_members_data()
    today_birthdays = []
    
    for member in all_members:
        dob_str = member.get('Data_Nascimento')
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, '%d/%m/%Y')
                if dob.day == day and dob.month == month:
                    today_birthdays.append(member)
            except ValueError:
                continue
    
    return today_birthdays
