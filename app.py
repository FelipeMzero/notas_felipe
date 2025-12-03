from flask import Flask, render_template, jsonify, request, send_file
import pandas as pd
import io
import time
import json
import os

# Define a pasta base como a pasta onde este arquivo (app.py) está localizado
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configura o Flask para procurar templates na pasta atual
app = Flask(__name__, template_folder=BASE_DIR, static_folder=BASE_DIR)

# Caminhos absolutos para os arquivos JSON (evita erros de arquivo não encontrado)
ARQUIVO_DISCIPLINAS = os.path.join(BASE_DIR, 'disciplinas.json')
ARQUIVO_NOTAS = os.path.join(BASE_DIR, 'notas.json')

# --- CONFIGURAÇÃO DE CORS ---
# Permite acesso mesmo se o frontend estiver em "preview" ou porta diferente
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# --- LÓGICA DE NEGÓCIO ---

def calcular_status(n1, n2, n3, rec=0.0):
    """
    Calcula a média e o status.
    Regra: Recuperação substitui a menor nota das 3, se for maior que ela.
    """
    try:
        n1, n2, n3, rec = float(n1), float(n2), float(n3), float(rec)
    except (ValueError, TypeError):
        n1 = n2 = n3 = rec = 0.0
        
    notas = [n1, n2, n3]
    
    # Lógica de substituição pela Recuperação
    if rec > 0:
        menor_nota = min(notas)
        if rec > menor_nota:
            # Encontra o índice da primeira ocorrência da menor nota e substitui
            idx_menor = notas.index(menor_nota)
            notas[idx_menor] = rec

    media = sum(notas) / 3.0
    
    # Definição de Status
    if n1 == 0 and n2 == 0 and n3 == 0 and rec == 0:
        status = "PENDENTE"
    elif media >= 6.0:
        status = "APROVADO"
    elif media > 0 and media < 6.0:
        # Se tem média mas reprovou, verificamos se cursou tudo
        if n3 == 0 and rec == 0:
             status = "CURSANDO"
        else:
             status = "REPROVADO"
    else:
        status = "PENDENTE"

    return {"media": round(media, 2), "status": status}

def carregar_dados():
    """
    Lê os JSONs, garante a integridade das listas de notas e retorna os dados compilados.
    """
    # 1. Carrega Disciplinas (Estrutura)
    if os.path.exists(ARQUIVO_DISCIPLINAS):
        with open(ARQUIVO_DISCIPLINAS, 'r', encoding='utf-8') as f:
            try:
                curriculo = json.load(f)
            except json.JSONDecodeError:
                curriculo = []
    else:
        curriculo = []

    # 2. Carrega Notas (Dados do Aluno)
    if os.path.exists(ARQUIVO_NOTAS):
        with open(ARQUIVO_NOTAS, 'r', encoding='utf-8') as f:
            try:
                historico = json.load(f)
            except json.JSONDecodeError:
                historico = {}
    else:
        historico = {}

    dados_compilados = []
    
    for disc in curriculo:
        codigo = disc["codigo"]
        # Obtém lista de notas ou cria padrão
        notas_salvas = historico.get(codigo, [0.0, 0.0, 0.0, 0.0])
        
        # NORMALIZAÇÃO CRÍTICA: Garante que a lista tenha sempre 4 elementos (float)
        # Se o JSON tiver [8, 9, 10], ele vira [8.0, 9.0, 10.0, 0.0]
        if not isinstance(notas_salvas, list):
            notas_salvas = [0.0, 0.0, 0.0, 0.0]
            
        while len(notas_salvas) < 4:
            notas_salvas.append(0.0)
            
        # Garante que são floats
        notas_salvas = [float(x) for x in notas_salvas[:4]]
            
        item = disc.copy()
        item['n1'] = notas_salvas[0]
        item['n2'] = notas_salvas[1]
        item['n3'] = notas_salvas[2]
        item['rec'] = notas_salvas[3]
        
        # Calcula dados derivados
        stats = calcular_status(item['n1'], item['n2'], item['n3'], item['rec'])
        item.update(stats)
        
        dados_compilados.append(item)
        
    return dados_compilados

def salvar_notas_json(codigo, n1, n2, n3, rec):
    """
    Lê o arquivo atual, atualiza a entrada específica e salva de volta.
    """
    # Lê o estado atual do arquivo para não perder outras disciplinas
    if os.path.exists(ARQUIVO_NOTAS):
        with open(ARQUIVO_NOTAS, 'r', encoding='utf-8') as f:
            try:
                historico = json.load(f)
            except json.JSONDecodeError:
                historico = {}
    else:
        historico = {}
        
    # Atualiza a disciplina específica
    historico[codigo] = [float(n1), float(n2), float(n3), float(rec)]
    
    # Escreve no disco
    with open(ARQUIVO_NOTAS, 'w', encoding='utf-8') as f:
        json.dump(historico, f, indent=2)

# --- ROTAS DA APLICAÇÃO ---

@app.route('/')
def index():
    # Passamos os dados iniciais via template para carregamento imediato
    dados_iniciais = carregar_dados()
    return render_template('index.html', dados=dados_iniciais)

@app.route('/api/dados')
def get_dados():
    # Rota usada pelo React para auto-refresh
    return jsonify(carregar_dados())

@app.route('/api/atualizar', methods=['POST'])
def atualizar_nota():
    """Recebe uma atualização pontual, salva e retorna o novo estado calculado."""
    try:
        req = request.json
        codigo = req.get('code')
        campo = req.get('field') # n1, n2, n3 ou rec
        valor = req.get('value')
        
        # 1. Carrega todos os dados para pegar o contexto atual da disciplina
        dados_atuais = carregar_dados()
        
        # Busca a disciplina na lista carregada
        disciplina_alvo = next((d for d in dados_atuais if d['codigo'] == codigo), None)
        
        if not disciplina_alvo:
            return jsonify({"error": "Disciplina não encontrada"}), 404

        # 2. Tratamento do valor recebido
        if valor == "" or valor is None:
            novo_valor = 0.0
        else:
            # Substitui vírgula por ponto e converte
            novo_valor = float(str(valor).replace(',', '.'))
        
        # Atualiza o campo no objeto em memória
        disciplina_alvo[campo] = novo_valor
        
        # 3. Salva no arquivo JSON (Persistência)
        salvar_notas_json(
            codigo, 
            disciplina_alvo['n1'], 
            disciplina_alvo['n2'], 
            disciplina_alvo['n3'], 
            disciplina_alvo['rec']
        )
        
        # 4. Recalcula status com os novos valores
        novos_stats = calcular_status(
            disciplina_alvo['n1'], 
            disciplina_alvo['n2'], 
            disciplina_alvo['n3'], 
            disciplina_alvo['rec']
        )
        disciplina_alvo.update(novos_stats)
        
        return jsonify({"success": True, "data": disciplina_alvo})

    except Exception as e:
        print(f"Erro ao atualizar: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/exportar_csv')
def exportar_csv():
    try:
        dados = carregar_dados()
        df = pd.DataFrame(dados)
        
        colunas_map = {
            'semestre': 'Semestre', 'codigo': 'Código', 'nome': 'Disciplina',
            'n1': 'Nota 1', 'n2': 'Nota 2', 'n3': 'Nota 3', 'rec': 'Recuperação',
            'media': 'Média', 'status': 'Status'
        }
        
        # Filtra colunas existentes
        cols_existentes = [c for c in colunas_map.keys() if c in df.columns]
        df_export = df[cols_existentes].rename(columns=colunas_map)
        
        buffer = io.BytesIO()
        # UTF-8 com BOM para abrir corretamente no Excel
        df_export.to_csv(buffer, index=False, sep=';', encoding='utf-8-sig')
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'Boletim_BSI_{int(time.time())}.csv',
            mimetype='text/csv'
        )
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    # debug=True permite recarregar o servidor ao salvar o arquivo
    app.run(debug=True, port=5000)