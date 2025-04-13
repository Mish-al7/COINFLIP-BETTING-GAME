# app.py - Main application file
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import random
from datetime import datetime
import decimal

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///coinflip.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Admin configuration - can be changed
HOUSE_EDGE = 0.05  # Default 5% house edge
WIN_PROBABILITY = 0.5 - (HOUSE_EDGE / 2)  # Default fair coin minus house edge
MAX_BET = 100.00  # Maximum bet amount in dollars

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    balance = db.Column(db.Float, default=0.00)
    is_admin = db.Column(db.Boolean, default=False)
    bets = db.relationship('Bet', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Bet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    choice = db.Column(db.String(5), nullable=False)  # 'heads' or 'tails'
    result = db.Column(db.String(5), nullable=False)  # 'heads' or 'tails'
    won = db.Column(db.Boolean, nullable=False)
    profit = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class AdminConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    win_probability = db.Column(db.Float, default=WIN_PROBABILITY)
    max_bet = db.Column(db.Float, default=MAX_BET)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Helper functions
def get_current_config():
    config = AdminConfig.query.order_by(AdminConfig.last_updated.desc()).first()
    if not config:
        config = AdminConfig(win_probability=WIN_PROBABILITY, max_bet=MAX_BET)
        db.session.add(config)
        db.session.commit()
    return config

def flip_coin(choice):
    config = get_current_config()
    # Determine if the user wins based on adjusted probability
    wins = random.random() < config.win_probability
    
    # Determine the result based on user choice and if they won
    if choice == 'heads':
        result = 'heads' if wins else 'tails'
    else:  # tails
        result = 'tails' if wins else 'heads'
        
    return result, wins

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('game'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('game'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        user_exists = User.query.filter_by(username=username).first()
        email_exists = User.query.filter_by(email=email).first()
        
        if user_exists:
            flash('Username already exists.')
            return redirect(url_for('register'))
        
        if email_exists:
            flash('Email already registered.')
            return redirect(url_for('register'))
        
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        # Give new users some starting funds
        new_user.balance = 100.00
        
        # Make first user an admin
        if User.query.count() == 0:
            new_user.is_admin = True
            
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created successfully! You can now log in.')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('game'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not user.check_password(password):
            flash('Invalid username or password')
            return redirect(url_for('login'))
            
        login_user(user)
        return redirect(url_for('game'))
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/game')
@login_required
def game():
    config = get_current_config()
    recent_bets = Bet.query.filter_by(user_id=current_user.id).order_by(Bet.timestamp.desc()).limit(10).all()
    return render_template('game.html', max_bet=config.max_bet, recent_bets=recent_bets)

@app.route('/place_bet', methods=['POST'])
@login_required
def place_bet():
    config = get_current_config()
    data = request.get_json()
    
    try:
        amount = float(data.get('amount', 0))
        choice = data.get('choice')
        
        # Validation
        if amount <= 0:
            return jsonify({'error': 'Bet amount must be greater than 0'}), 400
            
        if amount > config.max_bet:
            return jsonify({'error': f'Maximum bet is ${config.max_bet:.2f}'}), 400
            
        if amount > current_user.balance:
            return jsonify({'error': 'Insufficient funds'}), 400
            
        if choice not in ['heads', 'tails']:
            return jsonify({'error': 'Invalid choice'}), 400
            
        # Process bet
        result, won = flip_coin(choice)
        
        # Calculate profit/loss
        profit = amount if won else -amount
        
        # Update user balance
        current_user.balance += profit
        
        # Record bet
        new_bet = Bet(
            user_id=current_user.id,
            amount=amount,
            choice=choice,
            result=result,
            won=won,
            profit=profit
        )
        
        db.session.add(new_bet)
        db.session.commit()
        
        return jsonify({
            'result': result,
            'won': won,
            'profit': profit,
            'new_balance': current_user.balance
        })
        
    except ValueError:
        return jsonify({'error': 'Invalid bet amount'}), 400

@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
            if amount <= 0:
                flash('Deposit amount must be greater than 0')
                return redirect(url_for('deposit'))
                
            # In a real app, this would connect to a payment processor
            # For demo purposes, we'll just add the funds
            current_user.balance += amount
            db.session.commit()
            
            flash(f'Successfully deposited ${amount:.2f}')
            return redirect(url_for('game'))
            
        except ValueError:
            flash('Invalid deposit amount')
            return redirect(url_for('deposit'))
            
    return render_template('deposit.html')

@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
            if amount <= 0:
                flash('Withdrawal amount must be greater than 0')
                return redirect(url_for('withdraw'))
                
            if amount > current_user.balance:
                flash('Insufficient funds')
                return redirect(url_for('withdraw'))
                
            # In a real app, this would connect to a payment processor
            # For demo purposes, we'll just subtract the funds
            current_user.balance -= amount
            db.session.commit()
            
            flash(f'Successfully withdrew ${amount:.2f}')
            return redirect(url_for('game'))
            
        except ValueError:
            flash('Invalid withdrawal amount')
            return redirect(url_for('withdraw'))
            
    return render_template('withdraw.html')

@app.route('/profile')
@login_required
def profile():
    recent_bets = Bet.query.filter_by(user_id=current_user.id).order_by(Bet.timestamp.desc()).limit(20).all()
    
    # Calculate statistics
    total_bets = Bet.query.filter_by(user_id=current_user.id).count()
    wins = Bet.query.filter_by(user_id=current_user.id, won=True).count()
    losses = total_bets - wins
    
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    
    # Calculate profit/loss
    total_profit = db.session.query(db.func.sum(Bet.profit)).filter_by(user_id=current_user.id).scalar() or 0
    
    return render_template(
        'profile.html',
        recent_bets=recent_bets,
        total_bets=total_bets,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        total_profit=total_profit
    )

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if not current_user.is_admin:
        flash('Unauthorized access')
        return redirect(url_for('game'))
        
    config = get_current_config()
    
    if request.method == 'POST':
        try:
            new_probability = float(request.form.get('win_probability', 0))
            new_max_bet = float(request.form.get('max_bet', 0))
            
            # Validate inputs
            if not 0 <= new_probability <= 1:
                flash('Win probability must be between 0 and 1')
                return redirect(url_for('admin'))
                
            if new_max_bet <= 0:
                flash('Maximum bet must be greater than 0')
                return redirect(url_for('admin'))
                
            # Create new config
            new_config = AdminConfig(
                win_probability=new_probability,
                max_bet=new_max_bet,
                updated_by=current_user.id
            )
            
            db.session.add(new_config)
            db.session.commit()
            
            flash('Settings updated successfully')
            return redirect(url_for('admin'))
            
        except ValueError:
            flash('Invalid input')
            return redirect(url_for('admin'))
            
    # Get stats for admin dashboard
    total_bets = Bet.query.count()
    total_users = User.query.count()
    house_profit = db.session.query(db.func.sum(Bet.profit * -1)).scalar() or 0
    
    return render_template(
        'admin.html',
        config=config,
        total_bets=total_bets,
        total_users=total_users,
        house_profit=house_profit
    )

# Create database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)