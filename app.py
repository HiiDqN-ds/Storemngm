from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import random
import barcode
from barcode.writer import ImageWriter
from collections import defaultdict
from flask import jsonify

app = Flask(__name__)
app.secret_key = 'secret'  # Set a strong secret key for production


DATA_PATH = './data'
USERS_FILE = os.path.join(DATA_PATH, 'users.json')
ITEMS_FILE = os.path.join(DATA_PATH, 'items.json')
SALES_FILE = os.path.join(DATA_PATH, 'sales.json')
ORDERS_FILE = os.path.join(DATA_PATH, 'orders.json')
PAYMENTS_FILE = os.path.join(DATA_PATH, 'salary_payments.json')

# Helper to load JSON file
def load_json(file_path):
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump([], f)
    with open(file_path, 'r') as f:
        return json.load(f)

# Helper to save JSON file
def save_json(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

# Load all users
def load_users():
    return load_json(USERS_FILE)

# Save users
def save_users(users):
    save_json(USERS_FILE, users)

# Load items
def load_items():
    return load_json(ITEMS_FILE)

# Save items
def save_items(items):
    save_json(ITEMS_FILE, items)

# Load sales
def load_sales():
    return load_json(SALES_FILE)

# Save sales
def save_sales(sales):
    save_json(SALES_FILE, sales)


# Find user by username
def find_user(username):
    users = load_users()
    for user in users:
        if user['username'] == username:
            return user
    return None
from functools import wraps
def login_required(roles=None):
    if not isinstance(roles, (list, tuple)):
        roles = [roles] if roles else []

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                flash('Please login first', 'warning')
                return redirect(url_for('login'))
            if roles and session.get('role') not in roles:
                flash('Unauthorized access', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ROUTES

@app.route('/')
def index():
    if 'username' in session:
        if session['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('seller_dashboard'))
    return redirect(url_for('login'))

# Login
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = find_user(username)
        if user and check_password_hash(user['password'], password):
            if not user['activated']:
                flash('Your account is not activated yet.', 'warning')
                return redirect(url_for('login'))
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f'Welcome {username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'success')
    return redirect(url_for('login'))


# load_sales   
def load_sales():
    with open(SALES_FILE, 'r') as f:
        return json.load(f)
    
# load_purchases 
def load_purchases():
    with open(ORDERS_FILE, 'r') as f:
        return json.load(f)

# Date Time Format 
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d.%m.%Y'):
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime(format)
    except Exception:
        return value


from flask import session
from datetime import datetime


def calculate_all_time_profit(sales, items):
    barcode_map = {item['barcode']: item.get('purchase_price', 0) for item in items}
    profit = 0.0
    for s in sales:
        barcode = s.get('barcode')
        purchase_price = barcode_map.get(barcode, 0)
        sale_price = s.get('sale_price', 0)
        quantity = s.get('quantity', 0)
        profit += (sale_price - purchase_price) * quantity
    return round(profit, 2)

# Admin Dashboard
@app.route('/admin')
@login_required('admin')
def admin_dashboard():
    sales = load_sales()          # Load sales JSON data
    purchases = load_purchases()  # Load purchases JSON data
    items = load_items()          # Load item data (needed for purchase prices)

    now = datetime.now()
    today = now.date()

    # Parse sale dates (string -> datetime)
    for sale in sales:
        if isinstance(sale.get('date'), str):
            try:
                sale['date'] = datetime.fromisoformat(sale['date'])
            except ValueError:
                sale['date'] = datetime.min

    # Parse purchase dates (string -> datetime)
    for purchase in purchases:
        if isinstance(purchase.get('date'), str):
            try:
                purchase['date'] = datetime.fromisoformat(purchase['date'])
            except ValueError:
                purchase['date'] = datetime.min

    # Daily profit (today's sales total)
    daily_profit = sum(
        s.get('total_price', s.get('sale_price', 0) * s.get('quantity', 0))
        for s in sales
        if s['date'].date() == today
    )

    # Monthly profit = (monthly sales - monthly purchases)
    monthly_sales = sum(
        s.get('total_price', s.get('sale_price', 0) * s.get('quantity', 0))
        for s in sales
        if s['date'].year == now.year and s['date'].month == now.month
    )

    monthly_purchases = sum(
        p.get('total_price', p.get('buy_price', 0) * p.get('quantity', 0))
        for p in purchases
        if p['date'].year == now.year and p['date'].month == now.month
    )

    monthly_profit = monthly_sales - monthly_purchases

    # Total sales and purchases (all time)
    total_sales = sum(
        s.get('total_price', s.get('sale_price', 0) * s.get('quantity', 0))
        for s in sales
    )
    total_purchases = sum(
        p.get('total_price', p.get('buy_price', 0) * p.get('quantity', 0))
        for p in purchases
    )

    # Calculate all-time profit = total of (sale price - purchase price) * quantity
    barcode_to_purchase_price = {
        item['barcode']: item.get('purchase_price', 0) for item in items
    }

    all_time_profit = 0.0
    for s in sales:
        barcode = s.get('barcode')
        quantity = s.get('quantity', 0)
        sale_price = s.get('sale_price', 0)
        purchase_price = barcode_to_purchase_price.get(barcode, 0)
        profit = (sale_price - purchase_price) * quantity
        all_time_profit += profit

    all_time_profit = round(all_time_profit, 2)

    # Wallet balance = session or fallback to calculated
    wallet_balance = session.get('wallet_balance', total_sales - total_purchases)

    # Sort by date for display
    sales_sorted = sorted(sales, key=lambda x: x['date'], reverse=True)
    purchases_sorted = sorted(purchases, key=lambda x: x['date'], reverse=True)

    return render_template(
        "admin_dashboard.html",
        daily_profit=daily_profit,
        monthly_profit=monthly_profit,
        wallet_balance=wallet_balance,
        all_time_profit=all_time_profit,
        sales=sales_sorted,
        purchases=purchases_sorted
    )
def load_wallet_balance():
    kasse_file = os.path.join('data', 'kasse.json')
    balance = 0.0
    if os.path.exists(kasse_file):
        with open(kasse_file, 'r', encoding='utf-8') as f:
            try:
                transactions = json.load(f)
                balance = sum(t.get('amount', 0) for t in transactions)
            except json.JSONDecodeError:
                pass
    return round(balance, 2)

def format_currency_de(amount):
    return f"€{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# Set_wallet_balance
@app.route('/set_wallet_balance', methods=['POST'])
@login_required('admin')
def set_wallet_balance():
    wallet_balance = request.form.get('wallet_balance', type=float)
    if wallet_balance is not None and wallet_balance >= 0:
        session['wallet_balance'] = wallet_balance
        log_wallet_change(wallet_balance, change_type="manual")
        flash('Wallet-Bestand wurde aktualisiert.', 'success')
    else:
        flash('Ungültiger Betrag.', 'error')
    return redirect(url_for('admin_dashboard'))

def get_latest_wallet_balance():
    wallet_file = os.path.join('data', 'wallet.json')
    if os.path.exists(wallet_file):
        with open(wallet_file, 'r', encoding='utf-8') as f:
            try:
                log = json.load(f)
                if log:
                    return log[-1]['amount']  # last saved balance
            except json.JSONDecodeError:
                pass
    return 0.0  # fallback

#Saving Everyday History
def save_dashboard_snapshot(date, daily_profit, monthly_profit, wallet_balance, all_time_profit):
    history_file = os.path.join('data', 'dashboard_history.json')
    
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = []
    else:
        history = []

    # Avoid duplicate entry for the same day
    if any(entry.get("date") == date.isoformat() for entry in history):
        return

    history.append({
        "date": date.isoformat(),
        "daily_profit": round(daily_profit, 2),
        "monthly_profit": round(monthly_profit, 2),
        "wallet_balance": round(wallet_balance, 2),
        "all_time_profit": round(all_time_profit, 2)
    })

    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

#log_wallet_change
def log_wallet_change(amount, change_type="manual"):
    wallet_file = os.path.join('data', 'wallet_log.json')

    # Load old log
    if os.path.exists(wallet_file):
        with open(wallet_file, 'r', encoding='utf-8') as f:
            try:
                log = json.load(f)
            except json.JSONDecodeError:
                log = []
    else:
        log = []

    # Get the username from session
    username = session.get('username', 'unknown')

    # Append new entry
    log.append({
        "date": datetime.now().isoformat(),
        "change_type": change_type,
        "amount": round(amount, 2),
        "user": username
    })

    # Save updated log
    with open(wallet_file, 'w', encoding='utf-8') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)





def generate_csv(data, fieldnames):
    """Generate CSV response from list of dicts."""
    def generate():
        yield ",".join(fieldnames) + "\n"
        for row in data:
            yield ",".join(str(row.get(f, "")) for f in fieldnames) + "\n"
    return Response(generate(), mimetype='text/csv')

@app.route('/reset_wallet_balance', methods=['POST'])
def reset_wallet_balance():
    # Set wallet balance to zero in session or wherever you store it
    session['wallet_balance'] = 0.0

    flash("Wallet-Bestand wurde auf 0 zurückgesetzt.", "success")
    return redirect(url_for('admin_dashboard'))


# Download CSV routes

@app.route('/download/sales.csv')
@login_required('admin')
def download_sales_csv():
    sales = load_sales()
    fieldnames = ['date', 'product_name', 'quantity', 'price', 'total_price']
    return generate_csv(sales, fieldnames)

@app.route('/download/purchases.csv')
@login_required('admin')
def download_purchases_csv():
    purchases = load_purchases()
    fieldnames = ['date', 'product_name', 'quantity', 'price', 'total_price']
    return generate_csv(purchases, fieldnames)


# Seller Dashboard
@app.route('/seller')
@login_required('seller')
def seller_dashboard():
    username = session['username']
    sales = load_sales()  # Your function to load all sales
    users = load_users()  # Your function to load users
    items = load_items()  # Your function to load items

    # Get this seller's info
    seller = next((u for u in users if u['username'] == username), None)

    # Filter sales by this seller
    user_sales = [s for s in sales if s.get('seller') == username]

    # Helper function to get total sale amount for a sale record
    def get_sale_amount(sale):
        return sale.get('total_price') or (sale.get('sale_price', 0) * sale.get('quantity', 0))

    # Calculate daily income (today)
    today = datetime.now().date()
    daily_sales = [s for s in user_sales if datetime.fromisoformat(s['date']).date() == today]
    daily_income = sum(get_sale_amount(s) for s in daily_sales)

    # Total income from all sales
    total_income = sum(get_sale_amount(s) for s in user_sales)

    # Initialize monthly stats (last 6 months)
    now = datetime.now()
    monthly_income = defaultdict(float)
    monthly_expense = defaultdict(float)  # Adjust if you track expenses per sale
    monthly_profit = defaultdict(float)

    for i in range(6):
        month_key = (now - timedelta(days=30 * i)).strftime('%Y-%m')
        monthly_income[month_key] = 0.0
        monthly_expense[month_key] = 0.0
        monthly_profit[month_key] = 0.0

    # Calculate monthly income, expenses, and profit
    for sale in user_sales:
        sale_month = datetime.fromisoformat(sale['date']).strftime('%Y-%m')
        if sale_month in monthly_income:
            amount = get_sale_amount(sale)
            monthly_income[sale_month] += amount

            # Example expense calculation (if available)
            expense = sale.get('cost_price', 0) * sale.get('quantity', 0)
            monthly_expense[sale_month] += expense

            monthly_profit[sale_month] += amount - expense

    # Convert defaultdicts to regular dicts before sending to template
    monthly_income = dict(monthly_income)
    monthly_expense = dict(monthly_expense)
    monthly_profit = dict(monthly_profit)

    # Calculate total sales count
    total_sales = len(user_sales)

    # Calculate top 5 sold items for this seller
    item_counter = defaultdict(int)
    for sale in user_sales:
        item_counter[sale['barcode']] += sale.get('quantity', 1)

    top_items = sorted(item_counter.items(), key=lambda x: x[1], reverse=True)[:5]

    # Get item names for top sold items
    top_items_detail = [{
        'name': next((i.get('name', i.get('product_name', 'Unbenannt')) for i in items if i.get('barcode') == barcode), barcode),
        'quantity': qty
    } for barcode, qty in top_items]

    return render_template(
        "seller_dashboard.html",
        seller=seller,
        daily_income=daily_income,
        total_income=total_income,
        total_sales=total_sales,
        top_items=top_items_detail,
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        monthly_profit=monthly_profit
    )




# Admin: List Sellers
@app.route('/admin/sellers')
@login_required('admin')
def list_sellers():
    sellers = load_users()
    for seller in sellers:
        seller.setdefault('salary', 0.0)
        seller.setdefault('profile_img', '')
        seller.setdefault('activated', False)
    return render_template('sellers.html', sellers=sellers)

# Admin: Add Seller
@app.route('/admin/sellers/add', methods=['GET', 'POST'])
@login_required('admin')
def add_seller():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        profile_img = request.form.get('profile_img', '')
        salary = float(request.form.get('salary', 0.0))
        activated = 'activated' in request.form

        sellers = load_users()
        if any(s['username'] == username for s in sellers):
            flash('Username already exists', 'danger')
            return redirect(url_for('add_seller'))

        # ✅ Hash the password using scrypt or default PBKDF2
        hashed_password = generate_password_hash(password, method='scrypt')

        new_seller = {
            'username': username,
            'password': hashed_password,
            'role': 'seller',  # 🔒 Recommended: Always specify a role
            'profile_img': profile_img,
            'salary': salary,
            'activated': activated
        }

        sellers.append(new_seller)
        save_users(sellers)
        flash('Seller added successfully', 'success')
        return redirect(url_for('list_sellers'))

    return render_template('add_seller.html')



# Admin: Edit Seller
@app.route('/admin/sellers/edit/<username>', methods=['GET', 'POST'])
@login_required('admin')
def edit_seller(username):
    sellers = load_users()
    seller = next((s for s in sellers if s['username'] == username), None)
    if not seller:
        flash('Seller not found', 'danger')
        return redirect(url_for('list_sellers'))

    if request.method == 'POST':
        seller['profile_img'] = request.form.get('profile_img', seller.get('profile_img', ''))
        seller['salary'] = float(request.form.get('salary', seller.get('salary', 0.0)))
        seller['activated'] = 'activated' in request.form

        save_users(sellers)
        flash('Seller updated successfully', 'success')
        return redirect(url_for('list_sellers'))

    return render_template('edit_seller.html', seller=seller)


# Admin: Delete Seller
@app.route('/admin/sellers/delete/<username>', methods=['POST'])
@login_required('admin')
def delete_seller(username):
    sellers = load_users()
    sellers = [s for s in sellers if s['username'] != username]
    save_users(sellers)
    flash('Seller deleted successfully', 'success')
    return redirect(url_for('list_sellers'))

# Admin: List Items to Edit Barcode Generation
@app.route('/admin/items')
@login_required('admin')
def list_items():
    items = load_json(ITEMS_FILE)[::-1]  # newest items first

    for item in items:
        # Normalize product_name
        product_name = item.get('product_name')
        if not product_name or not str(product_name).strip():
            product_name = item.get('name', '').strip()

        if not product_name:
            product_name = "Unnamed product"

        item['product_name'] = product_name

        # Normalize other fields
        item['barcode'] = item.get('barcode', '')
        item['purchase_price'] = float(item.get('purchase_price', 0) or 0)
        item['selling_price'] = float(item.get('selling_price', 0) or 0)
        item['min_selling_price'] = float(item.get('min_selling_price', 0) or 0)
        item['quantity'] = int(item.get('quantity', 0) or 0)
        item['description'] = item.get('description', '')
        item['photo_link'] = item.get('image_url', '')

    return render_template('items.html',  items=items[::-1])


# Admin: List Items to Edit
import io
from flask import send_file
import barcode
from barcode.writer import ImageWriter

@app.route('/admin/items/barcode_print/<barcode_value>')
@login_required('admin')
def barcode_print(barcode_value):
    CODE128 = barcode.get_barcode_class('code128')
    img_io = io.BytesIO()

    code = CODE128(barcode_value, writer=ImageWriter())
    code.write(img_io)
    img_io.seek(0)
    
    return send_file(
        img_io,
        mimetype='image/png',
        as_attachment=False  # open inline
    )
# Admin: List selled Items
@app.route('/admin/sales')
@login_required('admin')
def admin_sales():
    sales = load_sales()
    items = load_items()
    users = load_users()

    # Optional: enrich sales with item name and seller name for better display
    for sale in sales:
        sale['item_name'] = next((
        i.get('product_name') or i.get('name') or 'Unnamed'
        for i in items
        if i.get('barcode') == sale.get('barcode')
    ), 'Unknown Item')

        sale['seller_name'] = sale.get('seller', 'Unknown')
    sales = sales[::-1]
    return render_template('admin_sales.html', sales=sales)

@app.route('/admin/add_item', methods=['GET', 'POST'])
@login_required('admin')
def add_item():
    if request.method == 'POST':
        form_data = request.form
        barcode = form_data['barcode']

        items = load_json(ITEMS_FILE)

        # ✅ Check for duplicate barcode
        if any(item.get('barcode') == barcode for item in items):
            flash(f'⚠️ Ein Artikel mit dem Barcode "{barcode}" existiert bereits!', 'danger')
            return redirect(url_for('add_item'))

        new_item = {
            "name": form_data['name'],
            "barcode": barcode,
            "purchase_price": float(form_data['purchase_price']),
            "selling_price": float(form_data['selling_price']),
            "min_selling_price": float(form_data['min_selling_price']),
            "quantity": int(form_data['quantity']),
            "photo_link": form_data.get('photo_link', ''),
            "description": form_data.get('description', ''),
            "seller": session.get('username', 'unknown')
        }

        items.append(new_item)
        save_json(ITEMS_FILE, items)
        flash('✅ Neuer Artikel hinzugefügt.', 'success')
        return redirect(url_for('list_items'))

    return render_template('add_item.html', item=None)





# Admin: Edit Item
@app.route('/admin/items/edit/<barcode>', methods=['GET', 'POST'])
@login_required('admin')
def edit_item(barcode):
    items = load_json(ITEMS_FILE)

    # Find the item by barcode (or other unique id)
    item = next((i for i in items if i.get('barcode') == barcode), None)
    if not item:
        flash("Artikel nicht gefunden.", "danger")
        return redirect(url_for('list_items'))

    if request.method == 'POST':
        # Check if barcode should be updated
        if 'edit_barcode' in request.form:
            new_barcode = request.form.get('barcode').strip()
            if new_barcode and new_barcode != item.get('barcode'):
                # Optionally: check if new_barcode is unique here
                item['barcode'] = new_barcode
        else:
            # Keep old barcode
            item['barcode'] = request.form.get('old_barcode')

        # Update other fields safely
        item['product_name'] = request.form.get('name', '').strip()
        item['purchase_price'] = float(request.form.get('purchase_price', 0))
        item['selling_price'] = float(request.form.get('selling_price', 0))
        item['min_selling_price'] = float(request.form.get('min_selling_price', 0))
        item['quantity'] = int(request.form.get('quantity', 0))
        item['description'] = request.form.get('description', '').strip()
        item['photo_link'] = request.form.get('photo_link', '').strip()

        # Save the updated items list back to JSON
        save_json(ITEMS_FILE, items)
        flash("Artikel wurde erfolgreich aktualisiert.", "success")
        return redirect(url_for('list_items'))

    # GET request: show form with item data
    return render_template('edit_item.html', item=item)

# Admin: Delete Item
@app.route('/admin/items/delete/<barcode>', methods=['POST'])
@login_required('admin')
def delete_item(barcode):
    items = load_items()
    items = [item for item in items if item['barcode'] != barcode]
    save_items(items)
    flash('Item deleted', 'success')
    return redirect(url_for('list_items'))

# Admim 🗑️ Delete Sale
@app.route('/admin/sales/delete/<int:index>', methods=['POST'])
@login_required('admin')
def delete_sale(index):
    sales = load_sales()
    if 0 <= index < len(sales):
        deleted_sale = sales.pop(index)
        save_sales(sales)
        flash(f"🗑️ Verkauf von {deleted_sale['quantity']} × {deleted_sale.get('barcode', 'unbekannt')} gelöscht.", "warning")
    else:
        flash("❌ Ungültiger Eintrag.", "danger")
    return redirect(url_for('admin_sales'))

 
# Admin ✏️ Update Sale
@app.route('/admin/sales/edit/<int:index>', methods=['GET', 'POST'])
@login_required('admin')
def edit_sale(index):
    sales = load_sales()
    if not (0 <= index < len(sales)):
        flash("❌ Verkauf nicht gefunden.", "danger")
        return redirect(url_for('admin_sales'))

    sale = sales[index]

    if request.method == 'POST':
        try:
            sale['quantity'] = int(request.form['quantity'])
            sale['sale_price'] = float(request.form['sale_price'])
            sale['total_price'] = round(sale['quantity'] * sale['sale_price'], 2)
            save_sales(sales)
            flash("✅ Verkauf aktualisiert.", "success")
        except Exception as e:
            flash(f"❌ Fehler beim Aktualisieren: {str(e)}", "danger")
        return redirect(url_for('admin_sales'))

    return render_template('edit_sale.html', sale=sale, index=index)



# Seller Dashboard
@app.route('/sell', methods=['GET', 'POST'])
def sell_item():
    # Access control: only admin or seller can sell
    if 'username' not in session or session.get('role') not in ('admin', 'seller'):
        flash("❌ Zugriff verweigert. Bitte einloggen.", 'danger')
        return redirect(url_for('login'))

    items = load_items()

    if request.method == 'POST':
        # Get all form indices: items[0][barcode], items[1][quantity], etc.
        indices = {
            key.split('[')[1].split(']')[0]
            for key in request.form if key.startswith('items[')
        }
        indices = sorted(indices, key=int)

        sales = load_sales()  # Load once before loop

        for idx in indices:
            barcode = request.form.get(f'items[{idx}][barcode]', '').strip()
            quantity_raw = request.form.get(f'items[{idx}][quantity]', '').strip()
            discount_active = request.form.get(f'items[{idx}][discount_active]')
            price_input = request.form.get(f'items[{idx}][price]', '').strip()

            # Validate barcode
            if not barcode:
                flash(f"❌ Bitte wählen Sie für Produkt {int(idx)+1} ein Produkt aus.", 'danger')
                return redirect(url_for('sell_item'))

            # Find the item in stock
            item = next((i for i in items if i.get('barcode') == barcode), None)
            if not item:
                flash(f"❌ Produkt mit Barcode {barcode} nicht gefunden.", 'danger')
                return redirect(url_for('sell_item'))

            # Validate quantity
            try:
                quantity = int(quantity_raw)
                if quantity <= 0:
                    raise ValueError()
            except ValueError:
                flash(f"❌ Ungültige Menge für Produkt {item.get('name', 'Produkt')}.", 'danger')
                return redirect(url_for('sell_item'))

            if quantity > item.get('quantity', 0):
                flash(f"❌ Nicht genug Bestand für Produkt {item.get('name', 'Produkt')}. Nur noch {item.get('quantity', 0)} verfügbar.", 'danger')
                return redirect(url_for('sell_item'))

            # Get sale price
            if discount_active:
                try:
                    sale_price = float(price_input)
                    if sale_price <= 0:
                        raise ValueError()
                except ValueError:
                    flash(f"❌ Ungültiger Preis für Produkt {item.get('name', 'Produkt')}.", 'danger')
                    return redirect(url_for('sell_item'))
            else:
                try:
                    sale_price = float(item.get('selling_price', 0))
                    if sale_price <= 0:
                        raise ValueError()
                except (ValueError, TypeError):
                    flash(f"❌ Das Produkt {item.get('name', 'Produkt')} hat einen ungültigen Preis.", 'danger')
                    return redirect(url_for('sell_item'))

            # Reduce stock
            item['quantity'] -= quantity
            purchase_price = item.get('purchase_price', 0)
            # Append sale with item name
            sales.append({
            'seller': session['username'],
            'barcode': barcode,
            'name': item.get('product_name') or item.get('name') or 'Unbenannt',
            'quantity': quantity,
            'sale_price': sale_price,
            'purchase_price': purchase_price,
            'total_price': round(sale_price * quantity, 2),
            'date': datetime.now().isoformat()
        })

            product_name = item.get("product_name") or item.get("name") or "Produkt"
            flash(f'✅ Verkauf von {quantity} × {product_name} erfolgreich.', 'success')


            # Low stock warning
            if item.get('quantity', 0) <= 5:
                flash(f'⚠️ Achtung: Nur noch {item.get("quantity", 0)} Stück von {item.get("name", "Produkt")} auf Lager!', 'warning')

        # Save everything once
        save_sales(sales)
        save_items(items)

        # Redirect to appropriate dashboard
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('seller_dashboard'))

    # GET: render form
    return render_template('sell_item.html', items=items)



# Seller: Seller History
@app.route('/seller/sales', methods=['GET', 'POST'])
@login_required('seller')
def seller_sales():
    sales = load_sales()
    username = session['username']

    # Filter sales nur vom angemeldeten Verkäufer
    user_sales = [s for s in sales if s['seller'] == username]

    if request.method == 'POST':
        sale_id = request.form.get('sale_id')
        new_quantity = request.form.get('quantity')
        new_price = request.form.get('sale_price')

        if not sale_id or not new_quantity or not new_price:
            flash("Alle Felder sind erforderlich.", "danger")
            return redirect(url_for('seller_sales'))

        try:
            sale_id = int(sale_id)
            new_quantity = int(new_quantity)
            new_price = float(new_price)
            if new_quantity <= 0 or new_price <= 0:
                raise ValueError
        except ValueError:
            flash("Bitte gültige Zahlen für Menge und Preis eingeben.", "danger")
            return redirect(url_for('seller_sales'))

        sale = next((s for s in sales if s['id'] == sale_id and s['seller'] == username), None)
        if not sale:
            flash("Verkauf nicht gefunden oder kein Zugriff.", "danger")
            return redirect(url_for('seller_sales'))

        sale['quantity'] = new_quantity
        sale['sale_price'] = new_price
        sale['total_price'] = round(new_quantity * new_price, 2)
        sale['date'] = datetime.now().isoformat()

        save_sales(sales)
        flash("Verkauf erfolgreich aktualisiert.", "success")
        return redirect(url_for('seller_sales'))

    user_sales = user_sales[::-1]
    return render_template('seller_sales.html', sales=user_sales)


# Salary Payment
@app.route('/admin/pay-salary', methods=['GET', 'POST'])
@login_required('admin')
def pay_salary():
    users = load_users()  # 
    if request.method == 'POST':
        employee = request.form['employee_name']
        amount = float(request.form['salary_amount'])
        source = request.form['payment_source']
        note = request.form.get('note', '')

        record = {
            'employee': employee,
            'amount': amount,
            'source': source,
            'note': note,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M')
        }

        save_salary_payment(record)  # ا
        flash(f'تم دفع {amount} ل.س لـ {employee} من {source}', 'success')
        return redirect(url_for('pay_salary'))

    return render_template('pay_salary.html', users=users)


from flask import request, session, flash, redirect, url_for, render_template
import os
import json
import random
from datetime import datetime
from werkzeug.utils import secure_filename
import barcode
from barcode.writer import ImageWriter

@app.route('/order', methods=['GET', 'POST'])
def order():
    if session.get('role') not in ['admin', 'seller']:
        flash('Zugriff verweigert.', 'danger')
        return redirect(url_for('index'))

    numero_unique = None

    if request.method == 'POST':
        try:
            product_name = request.form['product_name'].strip()
            ref_number = request.form.get('ref_number', '').strip()
            description = request.form.get('description', '').strip()
            price = float(request.form['price'])
            selling_price = float(request.form['selling_price'])
            min_selling_price = float(request.form['min_selling_price'])
            quantity = int(request.form['quantity'])

            # Validate prices and quantity positive
            if price < 0 or selling_price < 0 or min_selling_price < 0 or quantity < 1:
                raise ValueError("Preise und Menge müssen positiv sein.")
        except (ValueError, KeyError) as e:
            flash('Ungültige Eingabe: ' + str(e), 'danger')
            return redirect(url_for('order'))

        total_price = round(price * quantity, 2)
        today = datetime.now().strftime('%Y-%m-%d')
        username = session.get('username', 'unbekannt')

        # Generate unique 12-digit barcode
        def generate_unique_barcode():
            while True:
                code = ''.join(str(random.randint(0, 9)) for _ in range(12))
                exists = False
                if os.path.exists(ORDERS_FILE):
                    with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
                        try:
                            orders = json.load(f)
                            if any(o.get('order_number') == code for o in orders):
                                exists = True
                        except json.JSONDecodeError:
                            pass
                if os.path.exists(ITEMS_FILE):
                    with open(ITEMS_FILE, 'r', encoding='utf-8') as f:
                        try:
                            items = json.load(f)
                            if any(i.get('barcode') == code for i in items):
                                exists = True
                        except json.JSONDecodeError:
                            pass
                if not exists:
                    return code

        numero_unique = generate_unique_barcode()

        # Save barcode image
        barcode_dir = os.path.join(app.static_folder, 'barcodes')
        os.makedirs(barcode_dir, exist_ok=True)
        barcode_path = os.path.join(barcode_dir, f'code_barres_{numero_unique}')
        ean = barcode.get_barcode_class('ean13')
        code = ean(numero_unique, writer=ImageWriter())
        code.save(barcode_path)

        # Handle photo upload if present
        photo_filename = ""
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and allowed_file(photo.filename):
                ext = photo.filename.rsplit('.', 1)[1].lower()
                filename = f"{numero_unique}.{ext}"
                secure_name = secure_filename(filename)
                photo.save(os.path.join(UPLOAD_FOLDER, secure_name))
                photo_filename = f"uploads/{secure_name}"

        new_order = {
            "order_number": numero_unique,
            "product_name": product_name,
            "ref_number": ref_number,
            "description": description,
            "price": price,
            "selling_price": selling_price,
            "min_selling_price": min_selling_price,
            "quantity": quantity,
            "total_price": total_price,
            "date": today,
            "user": username,
            "barcode": f"barcodes/code_barres_{numero_unique}",
            "photo": photo_filename
        }

        # Load existing orders
        orders = []
        if os.path.exists(ORDERS_FILE):
            with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
                try:
                    orders = json.load(f)
                except json.JSONDecodeError:
                    orders = []

        orders.append(new_order)
        with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(orders, f, indent=2, ensure_ascii=False)

        # Update inventory items.json
        items = []
        if os.path.exists(ITEMS_FILE):
            with open(ITEMS_FILE, 'r', encoding='utf-8') as f:
                try:
                    items = json.load(f)
                except json.JSONDecodeError:
                    items = []

        found = False
        for item in items:
            if item.get('product_name') == product_name:
                item['quantity'] = item.get('quantity', 0) + quantity
                item['purchase_price'] = price
                item['selling_price'] = selling_price
                item['min_selling_price'] = min_selling_price
                item['description'] = description
                if photo_filename:
                    item['photo_link'] = photo_filename
                found = True
                break

        if not found:
            new_item = {
                "product_name": product_name,
                "barcode": numero_unique,
                "purchase_price": price,
                "selling_price": selling_price,
                "min_selling_price": min_selling_price,
                "quantity": quantity,
                "photo_link": photo_filename,
                "description": description,
                "seller": username
            }
            items.append(new_item)

        with open(ITEMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

        flash('Bestellung erfolgreich aufgegeben und Inventar aktualisiert!', 'success')
        return redirect(url_for('list_orders'))

    return render_template('order_item.html', numero_unique=numero_unique)


def load_items_for_seller(username):
    all_items = load_items()
    return [item for item in all_items if item.get('seller') == username]


# Load normalize_items
def normalize_items(items):
    for item in items:
        item['name'] = item.get('name') or item.get('product_name') or 'Unbenannt'
        item['product_name'] = item.get('product_name') or item.get('name') or 'Unbenannt'
        item['barcode'] = item.get('barcode', '')
        item['quantity'] = int(item.get('quantity', 0))
        item['purchase_price'] = float(item.get('purchase_price', 0))
        item['selling_price'] = float(item.get('selling_price', 0))
        item['min_selling_price'] = float(item.get('min_selling_price', 0))
        item['price'] = float(item.get('price', item.get('selling_price', 0)))
        item['description'] = item.get('description', '')
        item['photo_link'] = item.get('photo_link') or item.get('image_url', '')
    return items

def load_items():
    items = load_json(ITEMS_FILE)
    return normalize_items(items)

# Load Items for User/Seller
def load_items_for_seller(username):
    all_items = load_items()
    filtered_items = []
    for item in all_items:
        seller = item.get('seller', 'admin')  # Default to admin if missing
        if seller in ('admin', username):
            filtered_items.append(item)
    return filtered_items


# List all the items for the seller
@app.route('/seller/items')
@login_required('seller')
def seller_items():
    username = session['username']
    items = load_items_for_seller(username)
    items = normalize_items(items)  # Ensure all items have 'name'
    items = items[::-1]
    return render_template('seller_items.html', items=items)




# List all the Orders
@app.route('/orders')
def list_orders():
    # Use cross-platform path to the orders file
    order_file = os.path.join(os.path.dirname(__file__), 'data', 'orders.json')
    print(f"Looking for orders file at: {order_file}")  # Debug line (visible in Render logs)

    # Role-based access check
    if session.get('role') not in ['admin', 'seller']:
        flash('Zugriff verweigert.', 'danger')
        return redirect(url_for('index'))

    # Load orders from file
    orders = []
    if os.path.exists(order_file):
        try:
            with open(order_file, 'r', encoding='utf-8') as f:
                orders = json.load(f)
        except json.JSONDecodeError:
            print("JSON decode error in orders.json")
            orders = []
    else:
        print("orders.json file not found")

    # Optional filtering from query parameters
    user_filter = request.args.get('user', '')
    date_filter = request.args.get('date', '')

    if user_filter:
        orders = [o for o in orders if o.get('user') == user_filter]

    if date_filter:
        orders = [o for o in orders if o.get('date') == date_filter]

    # Get unique users for dropdown
    unique_users = sorted(set(o.get('user') for o in orders if 'user' in o))
    orders = orders[::-1]
    return render_template('list_orders.html', orders=orders, users=unique_users)





# Orders CRUD
# Edit Route
# Edit Route
@app.route('/orders/edit/<int:index>', methods=['GET', 'POST'])
@login_required()
def edit_order(index):
    if session.get('role') not in ['admin', 'seller']:
        flash('Zugriff verweigert.', 'danger')
        return redirect(url_for('index'))

    # Load existing orders
    with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
        try:
            orders = json.load(f)
        except json.JSONDecodeError:
            flash("Fehler beim Laden der Bestellungen.", "danger")
            return redirect(url_for('list_orders'))

    if index >= len(orders):
        flash('Bestellung nicht gefunden.', 'danger')
        return redirect(url_for('list_orders'))

    order = orders[index]

    if request.method == 'POST':
        try:
            order['product_name'] = request.form.get('product_name', order.get('product_name'))
            order['ref_number'] = request.form.get('ref_number', order.get('ref_number'))
            order['description'] = request.form.get('description', order.get('description'))
            order['price'] = float(request.form.get('price', order.get('price', 0)))
            order['quantity'] = int(request.form.get('quantity', order.get('quantity', 1)))
            order['purchase_price'] = float(request.form.get('purchase_price', order.get('purchase_price', 0)))
            order['selling_price'] = float(request.form.get('selling_price', order.get('selling_price', 0)))
            order['min_selling_price'] = float(request.form.get('min_selling_price', order.get('min_selling_price', 0)))

            # Optional: update photo link if provided
            photo_link = request.form.get('photo_link')
            if photo_link:
                order['photo_link'] = photo_link

            # Recalculate total
            order['total_price'] = round(order['price'] * order['quantity'], 2)

            # Save updated orders
            orders[index] = order
            with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(orders, f, indent=2, ensure_ascii=False)

            flash('Bestellung erfolgreich aktualisiert.', 'success')
            return redirect(url_for('list_orders'))
        except Exception as e:
            flash(f'Fehler beim Speichern: {e}', 'danger')
            return redirect(url_for('edit_order', index=index))

    return render_template('edit_order.html', order=order, index=index)


# Orders CRUD
# Delete Route
@app.route('/orders/delete/<int:index>', methods=['POST'])
@login_required()
def delete_order(index):
    try:
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            orders = json.load(f)

        if index < len(orders):
            orders.pop(index)
            with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(orders, f, indent=2, ensure_ascii=False)
            flash('Bestellung gelöscht.', 'success')
        else:
            flash('Ungültiger Index. Bestellung nicht gefunden.', 'danger')
    except Exception as e:
        flash(f'Fehler beim Löschen: {e}', 'danger')

    return redirect(url_for('list_orders'))


# save_salary_payment
def save_salary_payment(payment_record):
    # Load existing payments
    try:
        with open('data/salary_payments.json', 'r', encoding='utf-8') as f:
            payments = json.load(f)
    except FileNotFoundError:
        payments = []

    # Append new payment
    payments.append(payment_record)

    # Save back
    with open('data/salary_payments.json', 'w', encoding='utf-8') as f:
        json.dump(payments, f, ensure_ascii=False, indent=2)

# save_salary_payment
@app.route('/pay_salary', methods=['POST'], endpoint='pay_salary_post')
def pay_salary():
    record = request.get_json()  # JSON-Daten vom Client erhalten
    
    # Hier könntest du Validierungen machen, z.B. Felder prüfen
    if not record or 'employee_name' not in record or 'salary_amount' not in record or 'payment_source' not in record:
        return jsonify({'error': 'Ungültige Daten'}), 400
    
    # Speichern
    save_salary_payment(record)

    return jsonify({'message': 'Gehaltszahlung gespeichert!'}), 200

# List of Payments
@app.route('/list_salary_payments')
def list_salary_payments():
    try:
        with open('data/salary_payments.json', 'r', encoding='utf-8') as f:
            payments = json.load(f)
    except FileNotFoundError:
        payments = []
    payments = payments[::-1]
    return render_template('list_salary_payments.html', payments=payments)

 # Kasse
@app.route('/kasse', methods=['GET', 'POST'])
@login_required(['admin', 'seller'])
def kasse():
    kasse_file = os.path.join('data', 'kasse.json')
    transactions = []

    # Load existing transactions
    if os.path.exists(kasse_file):
        with open(kasse_file, 'r', encoding='utf-8') as f:
            try:
                transactions = json.load(f)
            except json.JSONDecodeError:
                transactions = []

    # Handle POST: add or delete
    if request.method == 'POST':
        if 'delete_index' in request.form and session.get('role') == 'admin':
            try:
                delete_index = int(request.form['delete_index'])
                if 0 <= delete_index < len(transactions):
                    deleted = transactions.pop(delete_index)
                    with open(kasse_file, 'w', encoding='utf-8') as f:
                        json.dump(transactions, f, indent=2, ensure_ascii=False)
                    flash(f"Eintrag gelöscht: {deleted.get('description', '')}", "success")
                else:
                    flash("Ungültiger Index", "danger")
            except Exception as e:
                flash(f"Fehler beim Löschen: {e}", "danger")
            return redirect(url_for('kasse'))

        try:
            amount = float(request.form['betrag'])
            description = request.form.get('beschreibung', '').strip()
            ktype = request.form.get('typ')  # "einzahlung" or "auszahlung"
            if ktype not in ['einzahlung', 'auszahlung']:
                raise ValueError("Ungültiger Typ")

            if ktype == 'auszahlung':
                amount = -abs(amount)
            else:
                amount = abs(amount)

            transaction = {
                "date": datetime.now().isoformat(),
                "amount": round(amount, 2),
                "type": ktype,
                "description": description,
                "user": session.get('username', 'unbekannt')
            }

            transactions.append(transaction)

            with open(kasse_file, 'w', encoding='utf-8') as f:
                json.dump(transactions, f, indent=2, ensure_ascii=False)

            flash(f"{ktype.capitalize()} gespeichert.", "success")
            return redirect(url_for('kasse'))

        except Exception as e:
            flash(f"Fehler: {e}", "danger")

    # 🧮 Calculate current balance
    current_balance = sum(t.get('amount', 0) for t in transactions)

    return render_template(
        "kasse.html",
        transactions=reversed(transactions),
        role=session.get('role'),
        current_balance=current_balance
    )



if __name__ == '__main__':
    if not os.path.exists(DATA_PATH):
        os.makedirs(DATA_PATH)
    # Ensure initial admin user exists
    users = load_users()
    if not any(u['role'] == 'admin' for u in users):
        users.append({
            'username': 'admin',
            'password': generate_password_hash('admin123'),
            'role': 'admin',
            'profile_img': '',
            'activated': True
        })
        save_users(users)
        print('Created default admin user: admin/admin123')
    app.run(debug=True)


