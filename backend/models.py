from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB # Usar JSONB para PostgreSQL
from datetime import datetime

db = SQLAlchemy() # Instância do SQLAlchemy, será inicializada no app.py

# Mantemos um modelo para o ciclo ATUAL, assumindo apenas um ciclo ativo por vez.
# Se precisar de múltiplos usuários, adicionaria um user_id aqui.
class CurrentCycle(db.Model):
    __tablename__ = 'current_cycle'
    id = db.Column(db.Integer, primary_key=True)
    gas_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    start_km = db.Column(db.Integer, nullable=True)
    end_km = db.Column(db.Integer, nullable=True)
    fuel_price_per_liter = db.Column(db.Numeric(10, 2), nullable=True)
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    start_time = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    # Dados acumulados DENTRO do ciclo
    cumulative_earnings = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    cumulative_race_count = db.Column(db.Integer, nullable=False, default=0)

    # Dados do PERÍODO atual (que são resetados ao arquivar período)
    current_period_earnings = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    current_period_race_count = db.Column(db.Integer, nullable=False, default=0)

    # Relacionamentos (o ciclo "tem" várias corridas e despesas)
    # cascade="all, delete-orphan": se o ciclo for deletado, deleta corridas/despesas associadas
    # lazy='dynamic': permite fazer queries adicionais nos relacionamentos (ex: cycle.earnings.count())
    earnings = db.relationship('Earning', backref='cycle', lazy='dynamic', cascade="all, delete-orphan")
    expenses = db.relationship('Expense', backref='cycle', lazy='dynamic', cascade="all, delete-orphan")

    def to_dict(self):
        """Converte o objeto Ciclo para um dicionário."""
        return {
            'id': self.id,
            'gas_cost': float(self.gas_cost) if self.gas_cost is not None else 0.0,
            'start_km': self.start_km,
            'end_km': self.end_km,
            'fuel_price_per_liter': float(self.fuel_price_per_liter) if self.fuel_price_per_liter is not None else None,
            'is_active': self.is_active,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'cumulative_earnings': float(self.cumulative_earnings) if self.cumulative_earnings is not None else 0.0,
            'cumulative_race_count': self.cumulative_race_count or 0,
            'current_period_earnings': float(self.current_period_earnings) if self.current_period_earnings is not None else 0.0,
            'current_period_race_count': self.current_period_race_count or 0,
        }


class Earning(db.Model):
    __tablename__ = 'earnings'
    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey('current_cycle.id'), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    def to_dict(self):
        """Converte o objeto Earning para um dicionário."""
        return {
            'id': self.id,
            'cycle_id': self.cycle_id,
            'timestamp': self.timestamp.isoformat(),
            'amount': float(self.amount)
        }


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey('current_cycle.id'), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    def to_dict(self):
        """Converte o objeto Expense para um dicionário."""
        return {
            'id': self.id,
            'cycle_id': self.cycle_id,
            'timestamp': self.timestamp.isoformat(),
            'category': self.category,
            'amount': float(self.amount)
        }


class Archive(db.Model):
    __tablename__ = 'archives'
    id = db.Column(db.Integer, primary_key=True)
    # Usamos JSONB para armazenar a estrutura complexa e flexível do arquivo
    archive_data = db.Column(JSONB, nullable=False)
    # Mantemos a data de arquivamento separada para facilitar ordenação/consulta
    archive_date = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Converte o objeto Archive para um dicionário."""
        # Acessamos o campo JSONB diretamente
        data = self.archive_data
        # Adicionamos o ID do banco e a data formatada se não estiverem no JSON
        data['db_id'] = self.id
        data['archiveDate'] = self.archive_date.isoformat() # Garante consistência
        return data
