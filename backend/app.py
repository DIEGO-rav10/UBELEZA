import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS # Importar CORS
from decimal import Decimal, InvalidOperation # Para lidar com números decimais
from datetime import datetime
import json # Para lidar com o arquivamento

# Importar configurações e modelos
from config import Config
from models import db, CurrentCycle, Earning, Expense, Archive # Importa db daqui

# Inicialização do App Flask
app = Flask(__name__)
app.config.from_object(Config)

# Inicialização das extensões
db.init_app(app)
migrate = Migrate(app, db)
CORS(app) # Habilita CORS para todas as rotas (ajuste se precisar de mais controle)

# --- Funções Auxiliares ---
def get_active_cycle():
    """Busca o ciclo ativo no banco de dados."""
    return CurrentCycle.query.filter_by(is_active=True).first()

def get_or_create_active_cycle():
    """Busca o ciclo ativo ou cria um novo se nenhum existir (mas não o ativa)."""
    cycle = get_active_cycle()
    if not cycle:
        # Cria um ciclo inicial inativo se o banco estiver vazio
        cycle = CurrentCycle(is_active=False)
        db.session.add(cycle)
        db.session.commit() # Salva para obter um ID
        # Recarrega para garantir que temos o objeto com ID
        cycle = CurrentCycle.query.get(cycle.id)
    return cycle

def calculate_and_update_cycle_totals(cycle):
    """Recalcula e atualiza totais do ciclo baseado nas corridas."""
    if not cycle:
        return

    total_earnings = db.session.query(db.func.sum(Earning.amount)).filter(Earning.cycle_id == cycle.id).scalar() or Decimal('0.0')
    total_races = cycle.earnings.count() # Usa o relacionamento lazy='dynamic'

    cycle.cumulative_earnings = total_earnings
    cycle.cumulative_race_count = total_races
    # Atualiza também os totais do período atual (assumindo que são os mesmos do ciclo neste modelo)
    cycle.current_period_earnings = total_earnings
    cycle.current_period_race_count = total_races
    db.session.commit()

# --- Rotas da API ---

@app.route('/api/state', methods=['GET'])
def get_app_state():
    """Retorna o estado atual completo do aplicativo."""
    cycle = get_or_create_active_cycle() # Garante que sempre temos um ciclo (mesmo inativo)
    earnings_list = [e.to_dict() for e in cycle.earnings.order_by(Earning.timestamp.asc()).all()] if cycle else []
    expenses_list = [e.to_dict() for e in cycle.expenses.order_by(Expense.timestamp.asc()).all()] if cycle else []
    archives_list = [a.to_dict() for a in Archive.query.order_by(Archive.archive_date.desc()).all()]

    return jsonify({
        'currentCycle': cycle.to_dict() if cycle else None,
        'earningsList': earnings_list,
        'expenseList': expenses_list,
        'archives': archives_list
    })

@app.route('/api/cycles/start', methods=['POST'])
def start_cycle():
    """Inicia um novo ciclo."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload inválido"}), 400

    gas_cost_str = data.get('gas_cost')
    start_km_str = data.get('start_km')
    fuel_price_str = data.get('fuel_price')

    try:
        gas_cost = Decimal(gas_cost_str) if gas_cost_str is not None else Decimal('0.0')
        if gas_cost <= 0:
             return jsonify({"error": "Custo da gasolina deve ser positivo"}), 400
    except (InvalidOperation, TypeError):
        return jsonify({"error": "Valor inválido para custo da gasolina"}), 400

    start_km = int(start_km_str) if start_km_str else None
    fuel_price = Decimal(fuel_price_str) if fuel_price_str else None

    # Desativa qualquer ciclo antigo que possa estar ativo (segurança)
    existing_active = get_active_cycle()
    if existing_active:
        existing_active.is_active = False
        db.session.add(existing_active)

    # Cria o novo ciclo
    new_cycle = CurrentCycle(
        gas_cost=gas_cost,
        start_km=start_km,
        fuel_price_per_liter=fuel_price,
        is_active=True,
        start_time=datetime.utcnow(),
        cumulative_earnings=Decimal('0.0'),
        cumulative_race_count=0,
        current_period_earnings=Decimal('0.0'),
        current_period_race_count=0
    )
    db.session.add(new_cycle)
    db.session.commit()

    return jsonify(new_cycle.to_dict()), 201 # 201 Created

@app.route('/api/cycles/finalize', methods=['POST'])
def finalize_cycle():
    """Finaliza o ciclo atual, arquivando-o."""
    cycle = get_active_cycle()
    if not cycle or not cycle.is_active:
        return jsonify({"error": "Nenhum ciclo ativo para finalizar"}), 400

    data = request.get_json() or {}
    end_km_str = data.get('end_km')
    note = data.get('note', '')

    try:
        end_km = int(end_km_str) if end_km_str is not None else cycle.start_km # Default to start_km if invalid/missing
        if cycle.start_km is not None and end_km < cycle.start_km:
             return jsonify({"error": f"KM Final ({end_km}) não pode ser menor que Inicial ({cycle.start_km})"}), 400
        cycle.end_km = end_km
    except (ValueError, TypeError):
         return jsonify({"error": "Valor inválido para KM final"}), 400

    # 1. Calcular dados finais para o arquivo
    earnings_list = [e.to_dict() for e in cycle.earnings.order_by(Earning.timestamp.asc()).all()]
    expenses_list = [e.to_dict() for e in cycle.expenses.order_by(Expense.timestamp.asc()).all()]
    total_other_expenses = sum(Decimal(exp['amount']) for exp in expenses_list)
    profit = cycle.cumulative_earnings - cycle.gas_cost - total_other_expenses
    km_driven = (cycle.end_km - cycle.start_km) if cycle.start_km is not None and cycle.end_km is not None and cycle.end_km >= cycle.start_km else 0
    km_per_liter = None
    cost_per_km = None
    if km_driven > 0 and cycle.gas_cost > 0 and cycle.fuel_price_per_liter is not None and cycle.fuel_price_per_liter > 0:
        liters_used = cycle.gas_cost / cycle.fuel_price_per_liter
        if liters_used > 0:
            km_per_liter = km_driven / float(liters_used) # float for potential division result
    if km_driven > 0:
         cost_per_km = (cycle.gas_cost + total_other_expenses) / Decimal(km_driven)


    # 2. Criar o objeto de arquivamento (usando a estrutura esperada pelo frontend)
    archive_payload = {
        "archiveDate": datetime.utcnow().isoformat(), # Armazenado no JSON e no campo DB
        "archiveType": "Ciclo Completo",
        "cycleEarnings": float(cycle.cumulative_earnings),
        "gasCost": float(cycle.gas_cost),
        "expensesList": expenses_list, # Lista de dicts
        "cycleRaceCount": cycle.cumulative_race_count,
        "startKM": cycle.start_km,
        "endKM": cycle.end_km,
        "fuelPricePerLiter": float(cycle.fuel_price_per_liter) if cycle.fuel_price_per_liter else None,
        "note": note,
        "summary_totalOtherExpenses": float(total_other_expenses),
        "summary_profit": float(profit),
        "summary_kmDriven": km_driven,
        "summary_kmPerLiter": f"{km_per_liter:.2f}" if km_per_liter is not None else "N/A",
        "summary_costPerKm": f"{cost_per_km:.2f}" if cost_per_km is not None else "N/A", # Formatando como string no JSON
        "periodEndDate": datetime.utcnow().isoformat(), # Data de finalização do ciclo
        "earningsDetails": earnings_list, # Lista de dicts
    }

    # 3. Salvar o Arquivo
    new_archive = Archive(archive_data=archive_payload, archive_date=datetime.utcnow())
    db.session.add(new_archive)

    # 4. Desativar e Resetar o ciclo atual (ou deletar e criar um novo inativo)
    # Optamos por desativar e limpar para manter o ID, mas deletar tb funciona
    cycle.is_active = False
    # Poderia resetar os campos aqui, mas ao buscar/criar um novo ciclo inativo resolve
    # Ex: cycle.gas_cost = 0 ... etc
    db.session.add(cycle)

    # Deletar corridas e despesas associadas (alternativa à cascade no modelo)
    # Earning.query.filter_by(cycle_id=cycle.id).delete()
    # Expense.query.filter_by(cycle_id=cycle.id).delete()

    db.session.commit()

    # Retorna o novo estado (sem ciclo ativo e listas vazias)
    new_state = get_app_state().get_json() # Chama a rota para obter o estado atualizado
    return jsonify(new_state)


# --- Rotas para Corridas (Earnings) ---

@app.route('/api/earnings', methods=['POST'])
def add_earning():
    """Adiciona uma nova corrida/ganho ao período/ciclo atual."""
    cycle = get_active_cycle()
    if not cycle or not cycle.is_active:
        return jsonify({"error": "Nenhum ciclo ativo para adicionar ganhos"}), 400

    data = request.get_json()
    if not data or 'amount' not in data or 'new_period_total' not in data:
        return jsonify({"error": "Payload inválido. 'amount' e 'new_period_total' são obrigatórios"}), 400

    try:
        # 'amount' aqui é a DIFERENÇA calculada pelo frontend
        amount = Decimal(data['amount'])
        new_period_total = Decimal(data['new_period_total'])
        timestamp_str = data.get('timestamp', datetime.utcnow().isoformat()) # Frontend pode mandar o timestamp exato
        timestamp = datetime.fromisoformat(timestamp_str)

        if amount < 0: # Correção de total (sem adicionar corrida)
             pass # Não cria Earning, apenas atualiza totais abaixo
        else:
            new_earning = Earning(
                cycle_id=cycle.id,
                amount=amount,
                timestamp=timestamp
            )
            db.session.add(new_earning)

        # Atualiza os totais do ciclo/período
        cycle.current_period_earnings = new_period_total
        cycle.cumulative_earnings += amount # Adiciona a diferença ao acumulado do ciclo
        # Incrementa contagem apenas se for um ganho positivo (nova corrida)
        if amount > 0:
            cycle.current_period_race_count += 1
            cycle.cumulative_race_count += 1

        db.session.add(cycle)
        db.session.commit()

        # Retorna o estado atualizado
        updated_state = get_app_state().get_json()
        return jsonify(updated_state)

    except (InvalidOperation, TypeError, ValueError) as e:
        db.session.rollback()
        return jsonify({"error": f"Dados inválidos: {e}"}), 400


@app.route('/api/earnings/<int:earning_id>', methods=['PUT'])
def edit_earning(earning_id):
    """Edita o valor de uma corrida existente."""
    cycle = get_active_cycle()
    if not cycle or not cycle.is_active:
        return jsonify({"error": "Ciclo inativo"}), 400

    earning = Earning.query.filter_by(id=earning_id, cycle_id=cycle.id).first()
    if not earning:
        return jsonify({"error": "Corrida não encontrada neste ciclo"}), 404

    data = request.get_json()
    if not data or 'amount' not in data:
        return jsonify({"error": "Payload inválido. 'amount' é obrigatório"}), 400

    try:
        new_amount = Decimal(data['amount'])
        if new_amount < 0:
            return jsonify({"error": "Valor da corrida não pode ser negativo"}), 400

        old_amount = earning.amount
        difference = new_amount - old_amount

        earning.amount = new_amount
        db.session.add(earning)

        # Reajusta totais do ciclo/período
        cycle.cumulative_earnings += difference
        cycle.current_period_earnings += difference # Assume que período reflete ciclo
        db.session.add(cycle)

        db.session.commit()

        updated_state = get_app_state().get_json()
        return jsonify(updated_state)

    except (InvalidOperation, TypeError):
        db.session.rollback()
        return jsonify({"error": "Valor inválido para amount"}), 400

@app.route('/api/earnings/<int:earning_id>', methods=['DELETE'])
def delete_earning(earning_id):
    """Exclui uma corrida."""
    cycle = get_active_cycle()
    if not cycle or not cycle.is_active:
        return jsonify({"error": "Ciclo inativo"}), 400

    earning = Earning.query.filter_by(id=earning_id, cycle_id=cycle.id).first()
    if not earning:
        return jsonify({"error": "Corrida não encontrada neste ciclo"}), 404

    amount_deleted = earning.amount
    db.session.delete(earning)

    # Reajusta totais do ciclo/período
    cycle.cumulative_earnings -= amount_deleted
    cycle.current_period_earnings -= amount_deleted
    cycle.cumulative_race_count -= 1
    cycle.current_period_race_count -= 1
    # Garante que não fiquem negativos
    cycle.cumulative_earnings = max(Decimal('0.0'), cycle.cumulative_earnings)
    cycle.current_period_earnings = max(Decimal('0.0'), cycle.current_period_earnings)
    cycle.cumulative_race_count = max(0, cycle.cumulative_race_count)
    cycle.current_period_race_count = max(0, cycle.current_period_race_count)

    db.session.add(cycle)
    db.session.commit()

    updated_state = get_app_state().get_json()
    return jsonify(updated_state)


# --- Rotas para Despesas (Expenses) ---

@app.route('/api/expenses', methods=['POST'])
def add_expense():
    """Adiciona uma nova despesa ao ciclo atual."""
    cycle = get_active_cycle()
    if not cycle or not cycle.is_active:
        return jsonify({"error": "Nenhum ciclo ativo para adicionar despesas"}), 400

    data = request.get_json()
    if not data or 'category' not in data or 'amount' not in data:
        return jsonify({"error": "Payload inválido. 'category' e 'amount' são obrigatórios"}), 400

    try:
        amount = Decimal(data['amount'])
        if amount <= 0:
            return jsonify({"error": "Valor da despesa deve ser positivo"}), 400

        timestamp_str = data.get('timestamp', datetime.utcnow().isoformat())
        timestamp = datetime.fromisoformat(timestamp_str)
        category = data['category']

        new_expense = Expense(
            cycle_id=cycle.id,
            category=category,
            amount=amount,
            timestamp=timestamp
        )
        db.session.add(new_expense)
        db.session.commit()

        # Não precisa recalcular totais do ciclo aqui, apenas retornar estado
        updated_state = get_app_state().get_json()
        return jsonify(updated_state), 201

    except (InvalidOperation, TypeError, ValueError) as e:
        db.session.rollback()
        return jsonify({"error": f"Dados inválidos: {e}"}), 400


@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
def delete_expense(expense_id):
    """Exclui uma despesa."""
    cycle = get_active_cycle()
    if not cycle or not cycle.is_active:
         # Permitir deletar mesmo se ciclo inativo? Talvez não.
        return jsonify({"error": "Ciclo inativo"}), 400

    expense = Expense.query.filter_by(id=expense_id, cycle_id=cycle.id).first()
    if not expense:
        return jsonify({"error": "Despesa não encontrada neste ciclo"}), 404

    db.session.delete(expense)
    db.session.commit()

    updated_state = get_app_state().get_json()
    return jsonify(updated_state)


# --- Rotas para Arquivos ---

@app.route('/api/archives', methods=['GET'])
def get_archives():
    """Lista todos os arquivos."""
    archives_list = [a.to_dict() for a in Archive.query.order_by(Archive.archive_date.desc()).all()]
    return jsonify(archives_list)

@app.route('/api/archives/period', methods=['POST'])
def archive_period():
    """Arquiva apenas o período atual (ganhos/corridas), resetando-os no ciclo."""
    cycle = get_active_cycle()
    if not cycle or not cycle.is_active:
        return jsonify({"error": "Nenhum ciclo ativo para arquivar período"}), 400

    if cycle.current_period_earnings <= 0 and cycle.current_period_race_count <= 0:
         return jsonify({"error": "Sem dados no período atual para arquivar"}), 400

    data = request.get_json() or {}
    note = data.get('note', '')

    # 1. Coleta dados do período atual do ciclo
    # Precisamos buscar as corridas *deste período* (neste modelo, são todas do ciclo)
    earnings_details_list = [e.to_dict() for e in cycle.earnings.order_by(Earning.timestamp.asc()).all()]
    period_end_date = datetime.utcnow() # Ou a data da última corrida? Usamos now.

    # 2. Calcula o lucro snapshot (considerando despesas TOTAIS do ciclo até agora)
    expenses_list = [e.to_dict() for e in cycle.expenses.order_by(Expense.timestamp.asc()).all()]
    total_other_expenses = sum(Decimal(exp['amount']) for exp in expenses_list)
    profit_snapshot = cycle.cumulative_earnings - cycle.gas_cost - total_other_expenses

    # 3. Cria payload do arquivo parcial
    archive_payload = {
        "archiveDate": period_end_date.isoformat(),
        "archiveType": "Período Parcial",
        "periodEarnings": float(cycle.current_period_earnings),
        "periodRaceCount": cycle.current_period_race_count,
        "periodEndDate": period_end_date.isoformat(),
        "earningsDetails": earnings_details_list, # Corridas até o momento
        "note": note,
        "gasCostSnapshot": float(cycle.gas_cost), # Gasolina do ciclo atual
        "cycleProfitSnapshot": float(profit_snapshot) # Lucro do ciclo até agora
    }

    # 4. Salva o Arquivo
    new_archive = Archive(archive_data=archive_payload, archive_date=period_end_date)
    db.session.add(new_archive)

    # 5. Reseta os dados do PERÍODO no ciclo atual
    cycle.current_period_earnings = Decimal('0.0')
    cycle.current_period_race_count = 0
    # IMPORTANTÍSSIMO: Deletar as corridas associadas a este período que foi arquivado.
    # No nosso modelo atual, período = ciclo, então deletamos TODAS as corridas do ciclo.
    cycle.earnings.delete() # Deleta todas as Earning associadas a este cycle_id

    # Atualiza também os acumulados do ciclo, já que as corridas foram removidas
    cycle.cumulative_earnings = Decimal('0.0')
    cycle.cumulative_race_count = 0

    db.session.add(cycle)
    db.session.commit()

    updated_state = get_app_state().get_json()
    return jsonify(updated_state)


@app.route('/api/archives/<int:archive_id>', methods=['DELETE'])
def delete_archive(archive_id):
    """Exclui um arquivo."""
    archive = Archive.query.get(archive_id)
    if not archive:
        return jsonify({"error": "Arquivo não encontrado"}), 404

    # Lógica extra se for "Período Parcial" e um ciclo estiver ativo
    cycle = get_active_cycle()
    archive_data = archive.archive_data # Pega o JSONB
    subtracted = False

    if cycle and cycle.is_active and archive_data.get("archiveType") == "Período Parcial":
        # Descontar valores do ciclo atual? É complexo e pode levar a inconsistências.
        # Por simplicidade, vamos apenas deletar o arquivo sem reajustar o ciclo ativo.
        # O usuário foi avisado no frontend.
        # Se precisar implementar:
        # earnings_to_add_back = Decimal(archive_data.get('periodEarnings', 0))
        # races_to_add_back = int(archive_data.get('periodRaceCount', 0))
        # cycle.cumulative_earnings += earnings_to_add_back # Ou current_period?
        # cycle.cumulative_race_count += races_to_add_back
        # db.session.add(cycle)
        # subtracted = True
        pass # Mantendo simples por enquanto

    db.session.delete(archive)
    db.session.commit()

    response_data = {"message": "Arquivo excluído."}
    # if subtracted:
    #     response_data["details"] = "Valores do período parcial NÃO foram reajustados no ciclo atual."

    # Retorna a lista atualizada de arquivos
    archives_list = [a.to_dict() for a in Archive.query.order_by(Archive.archive_date.desc()).all()]
    response_data["archives"] = archives_list
    return jsonify(response_data)


# --- Rotas para Edição Direta de Campos do Ciclo ---
# (Alternativa a ter rotas separadas para cada campo)

@app.route('/api/cycles/current', methods=['PUT'])
def update_cycle_fields():
    """Atualiza campos específicos do ciclo ativo."""
    cycle = get_active_cycle()
    if not cycle or not cycle.is_active:
        return jsonify({"error": "Nenhum ciclo ativo para atualizar"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload inválido"}), 400

    updated = False
    try:
        if 'gas_cost' in data:
            cycle.gas_cost = Decimal(data['gas_cost'])
            updated = True
        if 'fuel_price' in data:
            cycle.fuel_price_per_liter = Decimal(data['fuel_price']) if data['fuel_price'] is not None else None
            updated = True
        if 'start_km' in data:
            new_start_km = int(data['start_km']) if data['start_km'] is not None else None
            if cycle.end_km is not None and new_start_km is not None and new_start_km > cycle.end_km:
                 return jsonify({"error": f"KM inicial ({new_start_km}) não pode ser maior que KM final ({cycle.end_km})"}), 400
            cycle.start_km = new_start_km
            updated = True
        if 'end_km' in data:
            new_end_km = int(data['end_km']) if data['end_km'] is not None else None
            if cycle.start_km is not None and new_end_km is not None and new_end_km < cycle.start_km:
                 return jsonify({"error": f"KM final ({new_end_km}) não pode ser menor que KM inicial ({cycle.start_km})"}), 400
            cycle.end_km = new_end_km
            updated = True

        if updated:
            db.session.add(cycle)
            db.session.commit()
            updated_state = get_app_state().get_json()
            return jsonify(updated_state)
        else:
            return jsonify({"message": "Nenhum campo válido para atualizar foi fornecido"}), 400

    except (InvalidOperation, TypeError, ValueError) as e:
        db.session.rollback()
        return jsonify({"error": f"Dados inválidos: {e}"}), 400


# --- Rota de Reset (Opcional e Perigosa) ---
@app.route('/api/reset', methods=['POST'])
def reset_database():
    """Apaga TODOS os dados do banco. Use com EXTREMO cuidado."""
    # Adicionar alguma forma de confirmação extra ou autenticação aqui seria vital
    try:
        # Ordem importa por causa das Foreign Keys
        Earning.query.delete()
        Expense.query.delete()
        Archive.query.delete()
        CurrentCycle.query.delete()
        db.session.commit()
        # Cria um ciclo inicial inativo novamente
        get_or_create_active_cycle()
        return jsonify({"message": "Banco de dados resetado com sucesso."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Erro ao resetar o banco: {e}"}), 500


if __name__ == '__main__':
    app.run(debug=True)
