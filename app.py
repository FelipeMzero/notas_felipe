from flask import Flask, render_template, jsonify, request, send_file
import pandas as pd
import io
import time
import json
import os

app = Flask(__name__)

# Arquivos JSON
ARQUIVO_DISCIPLINAS = 'disciplinas.json'
ARQUIVO_NOTAS = 'notas.json'

# --- FUNÇÕES DE PERSISTÊNCIA ---

def carregar_dados():
    """Carrega estrutura e notas dos arquivos JSON"""
    # Carrega disciplinas
    if os.path.exists(ARQUIVO_DISCIPLINAS):
        with open(ARQUIVO_DISCIPLINAS, 'r', encoding='utf-8') as f:
            curriculo = json.load(f)
    else:
        curriculo = []

    # Carrega notas
    if os.path.exists(ARQUIVO_NOTAS):
        with open(ARQUIVO_NOTAS, 'r', encoding='utf-8') as f:
            historico = json.load(f)
    else:
        historico = {}

    dados_compilados = []
    
    for disc in curriculo:
        codigo = disc["codigo"]
        # Pega as notas salvas ou inicializa com zeros
        notas_salvas = historico.get(codigo, [0, 0, 0])
        # Garante que tenha pelo menos 3 posições
        while len(notas_salvas) < 3: notas_salvas.append(0)
        
        # Tenta pegar recuperação se existir (formato antigo era lista, novo pode precisar de ajuste se mudar estrutura)
        # Por compatibilidade com o JSON simples de lista [n1, n2, n3], vamos assumir rec=0 se não tiver no JSON
        # Se você quiser salvar Rec no JSON, o JSON de notas precisaria ser { "COD": {"notas": [], "rec": 0} }
        # Mas vamos manter o formato simples de lista e adicionar rec como o 4º elemento se necessário, 
        # ou gerenciar separadamente. Para simplificar, vou salvar a rec como 4º elemento da lista no JSON.
        
        rec = 0
        if len(notas_salvas) > 3:
            rec = notas_salvas[3]
        
        item = disc.copy()
        item['n1'] = notas_salvas[0]
        item['n2'] = notas_salvas[1]
        item['n3'] = notas_salvas[2]
        item['rec'] = rec
        
        # Calcula status
        item.update(calcular_status(item['n1'], item['n2'], item['n3'], item['rec']))
        dados_compilados.append(item)
        
    return dados_compilados

def salvar_notas(codigo, n1, n2, n3, rec):
    """Atualiza o arquivo notas.json"""
    if os.path.exists(ARQUIVO_NOTAS):
        with open(ARQUIVO_NOTAS, 'r', encoding='utf-8') as f:
            historico = json.load(f)
    else:
        historico = {}
        
    # Salva como lista de 4 elementos: [n1, n2, n3, rec]
    historico[codigo] = [float(n1), float(n2), float(n3), float(rec)]
    
    with open(ARQUIVO_NOTAS, 'w', encoding='utf-8') as f:
        json.dump(historico, f, indent=2)

def calcular_status(n1, n2, n3, rec=0):
    try:
        n1 = float(n1)
        n2 = float(n2)
        n3 = float(n3)
        rec = float(rec)
    except:
        n1, n2, n3, rec = 0.0, 0.0, 0.0, 0.0
        
    notas = [n1, n2, n3]
    
    # LÓGICA DE RECUPERAÇÃO
    if rec > 0:
        menor_nota = min(notas)
        if rec > menor_nota:
            idx_menor = notas.index(menor_nota)
            notas[idx_menor] = rec

    media = sum(notas) / 3
    
    if n1 == 0 and n2 == 0 and n3 == 0 and rec == 0:
        status = "PENDENTE"
    elif media >= 6.0:
        status = "APROVADO"
    elif media > 0 and media < 6.0:
        if n3 == 0 and rec == 0:
             status = "CURSANDO"
        else:
             status = "REPROVADO"
    else:
        status = "PENDENTE"

    return {"media": round(media, 2), "status": status}

# --- ROTAS FLASK ---

@app.route('/')
def index():
    # Recarrega dados do arquivo a cada request para garantir sincronia
    dados = carregar_dados()
    return render_template('index.html', dados=dados)

@app.route('/api/atualizar', methods=['POST'])
def atualizar_nota():
    req = request.json
    codigo = req.get('code')
    campo = req.get('field') # n1, n2, n3 ou rec
    valor = req.get('value')
    
    # Carrega estado atual
    dados_atuais = carregar_dados()
    disciplina_alvo = next((d for d in dados_atuais if d['codigo'] == codigo), None)
    
    if disciplina_alvo:
        try:
            if valor == "": valor = 0
            f_val = float(valor)
        except ValueError:
            return jsonify({"error": "Valor inválido"}), 400
        
        # Atualiza o campo temporariamente
        disciplina_alvo[campo] = f_val
        
        # Salva no JSON (Persistência)
        salvar_notas(
            codigo, 
            disciplina_alvo['n1'], 
            disciplina_alvo['n2'], 
            disciplina_alvo['n3'], 
            disciplina_alvo['rec']
        )
        
        # Recalcula status para retorno
        novos_stats = calcular_status(
            disciplina_alvo['n1'], 
            disciplina_alvo['n2'], 
            disciplina_alvo['n3'], 
            disciplina_alvo['rec']
        )
        disciplina_alvo.update(novos_stats)
        
        return jsonify({"success": True, "data": disciplina_alvo})
            
    return jsonify({"error": "Disciplina não encontrada"}), 404

@app.route('/exportar_csv')
def exportar_csv():
    dados = carregar_dados()
    df = pd.DataFrame(dados)
    
    df_export = df[['semestre', 'codigo', 'nome', 'n1', 'n2', 'n3', 'rec', 'media', 'status']].copy()
    df_export.columns = ['Semestre', 'Código', 'Disciplina', 'Nota 1', 'Nota 2', 'Nota 3', 'Recuperação', 'Média', 'Status']
    
    buffer = io.BytesIO()
    df_export.to_csv(buffer, index=False, sep=';', encoding='utf-8-sig')
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'Boletim_BSI_{int(time.time())}.csv',
        mimetype='text/csv'
    )

if __name__ == '__main__':
    # use_reloader=True ajuda no desenvolvimento, mas em produção usaria gunicorn/etc
    app.run(debug=True, port=5000)