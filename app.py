from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
import json, uuid, io, os, random, barcode
from datetime import datetime, timedelta
from barcode.writer import ImageWriter
from flask import jsonify,send_file
from functools import wraps


app = Flask(__name__)
app.secret_key = 'secret'  # Set a strong secret key for production


DATA_PATH = './data'
USERS_FILE = os.path.join(DATA_PATH, 'users.json')
ITEMS_FILE = os.path.join(DATA_PATH, 'items.json')
SALES_FILE = os.path.join(DATA_PATH, 'sales.json')
ORDERS_FILE = os.path.join(DATA_PATH, 'orders.json')
PAYMENTS_FILE = os.path.join(DATA_PATH, 'salary_payments.json')
ALERTS_DISMISS_FILE = os.path.join(DATA_PATH, 'dismissed_alerts.json')

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

# Login_required
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
    role = session.get('role')
    if role == 'admin':
        # redirect to seller_dashboard temporarily or show message
        return redirect(url_for('admin_dashboard'))
    elif role == 'seller':
        return redirect(url_for('seller_dashboard'))
    else:
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
def datetimeformat(value, format='%d.%m.%Y %H:%M'):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime(format)
    except Exception:
        return value

# calculate_all_time_profit
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





# Notifications
@app.route('/admin/notifications')
@login_required('admin')
def admin_notifications():
    # This should prepare mailbox_notifications same as your dashboard
    # Example (adjust according to your data source):
    mailbox_notifications = get_mailbox_notifications()  # Your existing function or logic
    
    return render_template("admin_notifications.html", mailbox_notifications=mailbox_notifications)


# Admin Daschboard
# Admin Dashboard
@app.route('/admin')
@login_required('admin')
def admin_dashboard():
    now = datetime.now()
    today = now.date()

    # Load data
    sales = load_sales()
    purchases = load_purchases()
    items = load_items()

    # Parse sales dates and calculate profits
    for sale in sales:
        if isinstance(sale.get('date'), str):
            try:
                sale['date'] = datetime.fromisoformat(sale['date'])
            except Exception:
                sale['date'] = datetime.min

        total_profit_per_sale = 0
        for item in sale.get('items', []):
            try:
                purchase_price = float(item.get('purchase_price', 0))
                sale_price = float(item.get('sale_price', 0))
                quantity = int(item.get('quantity', 0))
                profit = (sale_price - purchase_price) * quantity
                item['profit'] = round(profit, 2)
                total_profit_per_sale += profit
            except Exception:
                item['profit'] = 0
        sale['total_profit'] = round(total_profit_per_sale, 2)

    # Parse purchase dates
    for purchase in purchases:
        if isinstance(purchase.get('date'), str):
            try:
                purchase['date'] = datetime.fromisoformat(purchase['date'])
            except Exception:
                purchase['date'] = datetime.min

    # Profit calculations
    all_time_profit = round(sum(
        item['profit']
        for sale in sales
        for item in sale.get('items', [])
    ), 2)

    daily_sales_total = sum(
        item.get('total_price', 0)
        for sale in sales if sale['date'].date() == today
        for item in sale.get('items', [])
    )

    daily_purchases_total = sum(
        p.get('total_price', 0)
        for p in purchases if p['date'].date() == today
    )

    daily_profit = round(daily_sales_total - daily_purchases_total, 2)

    monthly_sales = sum(
        item.get('total_price', 0)
        for sale in sales if sale['date'].year == now.year and sale['date'].month == now.month
        for item in sale.get('items', [])
    )

    monthly_purchases = sum(
        p.get('total_price', 0)
        for p in purchases if p['date'].year == now.year and p['date'].month == now.month
    )

    monthly_profit = round(monthly_sales - monthly_purchases, 2)

    sales_sorted = sorted(sales, key=lambda x: x['date'], reverse=True)
    purchases_sorted = sorted(purchases, key=lambda x: x['date'], reverse=True)

    kasse_balance = load_kasse_balance()
    total_balance = round(kasse_balance - daily_purchases_total + daily_sales_total, 2)

    # 📬 Mailbox-style notifications
    mailbox_notifications = []
    threshold_date = now - timedelta(days=21)

    for item in items:
        # Check if date exists
        item_date_str = item.get('added_date') or item.get('date')
        try:
            item_date = datetime.fromisoformat(item_date_str)
        except:
            continue

        # Notification: Item older than 21 days
        if item_date < threshold_date:
            mailbox_notifications.append({
                'date': item_date_str,
                'message': f"📦 Produkt '{item.get('product_name', 'Unbekannt')}' ist seit { (now - item_date).days } Tagen im Lager.",
                'barcode': item.get('barcode', '')
            })

        # Notification: Quantity ≤ 5
        if item.get('quantity', 0) <= 5:
            mailbox_notifications.append({
                'date': now.isoformat(),
                'message': f"⚠️ Niedriger Lagerbestand für '{item.get('product_name', 'Unbekannt')}' – nur noch {item.get('quantity')} Stück!",
                'barcode': item.get('barcode', '')
            })
     # ========== Mailbox Notifications ==========
    mailbox_notifications = []
    today = datetime.today()

    for item in items:
        # Benachrichtigung, wenn Menge <= 5
        if item.get('quantity', 0) <= 5:
            mailbox_notifications.append({
                'date': today.isoformat(),
                'message': f"❗ Geringer Lagerbestand für Produkt: {item.get('product_name', 'Unbekannt')} (Menge: {item.get('quantity', 0)})",
                'barcode': item.get('barcode', 'unknown')
            })

        # Benachrichtigung, wenn Produkt älter als 21 Tage im Lager ist
        date_str = item.get('date_added') or item.get('date')
        try:
            date_added = datetime.fromisoformat(date_str)
            if (today - date_added).days > 21:
                mailbox_notifications.append({
                    'date': today.isoformat(),
                    'message': f"⏳ Produkt '{item.get('product_name', 'Unbekannt')}' ist seit über 21 Tagen im Lager.",
                    'barcode': item.get('barcode', 'unknown')
                })
        except Exception as e:
            print("Fehler beim Datum:", e)

    return render_template(
        "admin_dashboard.html",
        daily_profit=daily_profit,
        monthly_profit=monthly_profit,
        all_time_profit=all_time_profit,
        wallet_balance=kasse_balance,
        total_balance=total_balance,
        sales=sales_sorted,
        purchases=purchases_sorted,
        mailbox_notifications=mailbox_notifications
    )

# Seller_dashboard
@app.route('/seller')
@login_required('seller')
def seller_dashboard():
    username = session['username']

    sales_data = load_sales()
    orders = load_orders()

    user_orders = [order for order in sales_data if order.get('user') == username]
    user_purchases = [p for p in orders if p.get('user') == username]
    
    today = datetime.now().date()

    daily_sales_total = 0.0
    daily_purchases_total = 0.0  # <-- Initialize here
    daily_profit = 0
    monthly_profit = 0
    total_profit = 0
    monthly_total_order_price = 0

    # Calculate daily sales total and profits
    for order in user_orders:
        order_date = datetime.fromisoformat(order['date']) if order.get('date') else None

        if order_date:
            # Total daily sales (Umsatz)
            if order_date.date() == today:
                for item in order.get('items', []):
                    daily_sales_total += item.get('total_price', 0)

        order_profit = 0
        for item in order.get('items', []):
            item_profit = (item.get('sale_price', 0) - item.get('purchase_price', 0)) * item.get('quantity', 0)
            order_profit += item_profit

        if order_date:
            # Sum monthly profit
            if order_date.year == today.year and order_date.month == today.month:
                monthly_profit += order_profit
                monthly_total_order_price += order.get('total_order_price', 0)

            # Sum daily profit
            if order_date.date() == today:
                daily_profit += order_profit

        total_profit += order_profit

    # Calculate daily purchases total outside the order loop
    for purchase in user_purchases:
        purchase_date = datetime.fromisoformat(purchase.get('date')) if purchase.get('date') else None
        if purchase_date and purchase_date.date() == today:
            daily_purchases_total += purchase.get('price', 0) * purchase.get('quantity', 0)

    total_purchase_cost = sum(p.get('price', 0) * p.get('quantity', 0) for p in user_purchases)
    total_balance = daily_sales_total - daily_purchases_total
    print("user_purchases",orders)
    
    return render_template(
    'seller_dashboard.html',
    sales=user_orders,
    purchases=user_purchases,  # ✅ only seller's purchases!
    daily_profit=daily_profit,
    monthly_profit=monthly_profit,
    total_profit=total_profit,
    total_purchase_cost=total_purchase_cost,
    total_balance=total_balance,
    monthly_total_order_price=monthly_total_order_price,
    daily_sales_total=daily_sales_total,
    daily_purchases_total=daily_purchases_total
)


# Load_kasse_balance
def load_kasse_balance():
    kasse_file = os.path.join('data', 'kasse.json')
    transactions = []
    if os.path.exists(kasse_file):
        with open(kasse_file, 'r', encoding='utf-8') as f:
            try:
                transactions = json.load(f)
            except json.JSONDecodeError:
                pass
    return sum(t.get('amount', 0) for t in transactions)

# Format_currency_de
def format_currency_de(amount):
    return f"€{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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




 # Generate CSV
#Log generate_csv
def generate_csv(data, fieldnames):
    """Generate CSV response from list of dicts."""
    def generate():
        yield ",".join(fieldnames) + "\n"
        for row in data:
            yield ",".join(str(row.get(f, "")) for f in fieldnames) + "\n"
    return Response(generate(), mimetype='text/csv')

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

@app.route('/admin/sellers/add', methods=['GET', 'POST'])
@login_required('admin')
def add_seller():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        profile_img = request.form.get('profile_img', '').strip()
        salary_str = request.form.get('salary', '').strip()
        activated = 'activated' in request.form

        # Basic validation
        if not username:
            flash('Benutzername darf nicht leer sein.', 'danger')
            return redirect(url_for('add_seller'))

        if not password:
            flash('Passwort darf nicht leer sein.', 'danger')
            return redirect(url_for('add_seller'))

        # Convert salary safely
        try:
            salary = float(salary_str) if salary_str else 0.0
            if salary < 0:
                raise ValueError("Gehalt darf nicht negativ sein.")
        except ValueError as e:
            flash(f'Ungültiges Gehalt: {e}', 'danger')
            return redirect(url_for('add_seller'))

        # Load existing sellers
        sellers = load_users()
        if any(s['username'].lower() == username.lower() for s in sellers):
            flash('Benutzername existiert bereits.', 'danger')
            return redirect(url_for('add_seller'))

        # Hash the password securely
        hashed_password = generate_password_hash(password, method='scrypt')

        new_seller = {
            'username': username,
            'password': hashed_password,
            'role': 'seller',
            'profile_img': profile_img,
            'salary': salary,
            'activated': activated
        }

        sellers.append(new_seller)
        save_users(sellers)

        flash('Verkäufer erfolgreich hinzugefügt!', 'success')
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

    return render_template('items.html',  items=items)

# Admin: List Items to Edit
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


# Admin: admin_sales
@app.route('/admin/sales')
@login_required('admin')
def admin_sales():
    all_orders = load_sales()
    flattened_sales = []

    for order in all_orders:
        order_id = order.get('order_id')
        user = order.get('user')
        date = order.get('date')
        items = order.get('items', [])
        for item in items:
            flattened_sales.append({
                'order_id': order_id,
                'seller': user,
                'date': date,
                'barcode': item.get('barcode'),
                'product_name': item.get('product_name'),  # keep same as HTML template
                'quantity': item.get('quantity'),
                'sale_price': float(item.get('sale_price', 0)),
                'total_price': float(item.get('total_price', item.get('quantity', 0) * item.get('sale_price', 0)))
            })

    all_orders = load_sales()  # Full orders with items list and total_order_price
    return render_template('admin_sales.html', sales=all_orders[::-1])

@app.route('/admin/sales/edit/<order_id>/<barcode>', methods=['GET', 'POST'])
def edit_sale(order_id, barcode):
    sales = load_sales()

    # Suche Order mit order_id
    order = next((o for o in sales if o['order_id'] == order_id), None)
    if not order:
        flash('Bestellung nicht gefunden', 'danger')
        return redirect(url_for('admin_sales'))

    # Suche Artikel mit Barcode in dieser Order
    item = next((i for i in order.get('items', []) if i['barcode'] == barcode), None)
    if not item:
        flash('Artikel nicht gefunden', 'danger')
        return redirect(url_for('admin_sales'))

    if request.method == 'POST':
        try:
            item['quantity'] = int(request.form['quantity'])
            item['sale_price'] = float(request.form['sale_price'])
            # evtl. weitere Felder anpassen
            save_sales(sales)
            flash('Verkauf erfolgreich aktualisiert', 'success')
            return redirect(url_for('admin_sales'))
        except Exception as e:
            flash(f'Fehler beim Speichern: {e}', 'danger')

    return render_template('edit_sale.html', order_id=order_id, barcode=barcode, sale=item)

@app.route('/admin/sales/delete_sales_order/<order_id>', methods=['POST'])
@login_required('admin')
def delete_sales_order(order_id):
    sales = load_sales()
    updated_sales = [order for order in sales if order.get('order_id') != order_id]
    
    if len(updated_sales) == len(sales):
        flash("❌ Bestellung nicht gefunden.", "danger")
    else:
        save_sales(updated_sales)
        flash("✅ Bestellung erfolgreich gelöscht.", "warning")

    return redirect(url_for('admin_sales'))


# Add Item
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

        # ✅ Create new item with added_date
        new_item = {
            "name": form_data['name'],
            "barcode": barcode,
            "purchase_price": float(form_data['purchase_price']),
            "selling_price": float(form_data['selling_price']),
            "min_selling_price": float(form_data['min_selling_price']),
            "quantity": int(form_data['quantity']),
            "description": form_data.get('description', ''),
            "seller": session.get('username', 'unknown'),
           "added_date": datetime.now().strftime('%Y-%m-%d')# 🕒 Store timestamp
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

@app.route('/sell', methods=['GET', 'POST'])
def sell_item():
    # Access control: only admin or seller can sell
    if 'username' not in session or session.get('role') not in ('admin', 'seller'):
        flash("❌ Zugriff verweigert. Bitte einloggen.", 'danger')
        return redirect(url_for('login'))

    items = load_items()

    if request.method == 'POST':
        # Collect all indices from form
        indices = {
            key.split('[')[1].split(']')[0]
            for key in request.form if key.startswith('items[')
        }
        indices = sorted(indices, key=int)

        sales = load_sales()  # Load existing sales/orders

        order_items = []
        total_order_price = 0.0

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

            # Determine sale price
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

            # Calculate total price for this item
            total_price = round(sale_price * quantity, 2)
            total_order_price += total_price

            # Add item to order_items list
            order_items.append({
                'barcode': barcode,
                'product_name': item.get('product_name') or item.get('name') or 'Unbenannt',
                'quantity': quantity,
                'sale_price': sale_price,
                'total_price': total_price,
                'purchase_price': item.get('purchase_price', 0)
            })

            # Reduce stock quantity
            item['quantity'] -= quantity

            # Flash success per item
            product_name = item.get("product_name") or item.get("name") or "Produkt"
            flash(f'✅ Verkauf von {quantity} × {product_name} erfolgreich.', 'success')

            # Low stock warning
            if item.get('quantity', 0) <= 5:
                flash(f'⚠️ Achtung: Nur noch {item.get("quantity", 0)} Stück von {product_name} auf Lager!', 'warning')

        # Create a single order object with all items
        new_order = {
            "order_id": str(uuid.uuid4()),
            "user": session['username'],
            "date": datetime.now().isoformat(),
            "items": order_items,
            "total_order_price": round(total_order_price, 2)
        }

        # Append the new order
        sales.append(new_order)

        # Save updated sales and items
        save_sales(sales)
        save_items(items)

        # Redirect based on role
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('seller_dashboard'))

    # GET: render the sell form
    return render_template('sell_item.html', items=items)

# Seller: Seller History
@app.route('/seller/sales')
@login_required('seller')
def seller_sales():
    username = session.get('username', '').lower()
    
    # Load all sales (replace with your actual function)
    sales = load_sales()  # returns a list of sale dicts
    
    # Filter sales by matching user/seller - using .get() to avoid KeyError
    user_sales = [s for s in sales if s.get('user', '').lower() == username]
    
    # Optional: sort by date descending (if your sales have a 'date' field)
    user_sales.sort(key=lambda s: s.get('date', ''), reverse=True)
    
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


@app.route('/order', methods=['GET', 'POST'])
def order():
    if session.get('role') not in ['admin', 'seller']:
        flash('Zugriff verweigert.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            product_name = request.form['product_name'].strip()
            ref_number = request.form.get('ref_number', '').strip()
            description = request.form.get('description', '').strip()
            price = float(request.form['price'])
            selling_price = float(request.form['selling_price'])
            min_selling_price = float(request.form['min_selling_price'])
            quantity = int(request.form['quantity'])

            if price < 0 or selling_price < 0 or min_selling_price < 0 or quantity < 1:
                raise ValueError("Preise und Menge müssen positiv sein.")
        except (ValueError, KeyError) as e:
            flash('Ungültige Eingabe: ' + str(e), 'danger')
            return redirect(url_for('order'))

        today = datetime.now().strftime('%Y-%m-%d')
        username = session.get('username', 'unbekannt')

        # Load existing items
        items = []
        if os.path.exists(ITEMS_FILE):
            with open(ITEMS_FILE, 'r', encoding='utf-8') as f:
                try:
                    items = json.load(f)
                except json.JSONDecodeError:
                    pass

        # Function to generate a unique 12-digit barcode
        def generate_unique_barcode():
            while True:
                code = ''.join(str(random.randint(0, 9)) for _ in range(12))
                if not any(i.get('barcode') == code for i in items):
                    return code

        # Validate or generate barcode
        if ref_number:
            if not ref_number.isdigit() or len(ref_number) not in [12, 13]:
                flash("❌ Der manuell eingegebene Barcode muss genau 12 Ziffern lang sein.", "danger")
                return redirect(url_for('order'))
            
            if any(i.get('barcode') == ref_number for i in items):
                flash("❌ Der Barcode existiert bereits. Bitte wählen Sie einen anderen.", "danger")
                return redirect(url_for('order'))

            barcode_number = ref_number
        else:
            barcode_number = generate_unique_barcode()

        # Save barcode image
        barcode_dir = os.path.join(app.static_folder, 'barcodes')
        os.makedirs(barcode_dir, exist_ok=True)
        barcode_path = os.path.join(barcode_dir, f'code_barres_{barcode_number}')
        ean = barcode.get_barcode_class('ean13')
        code = ean(barcode_number, writer=ImageWriter())
        code.save(barcode_path)

        total_price = round(price * quantity, 2)

        new_order = {
            "order_number": barcode_number,
            "product_name": product_name,
            "ref_number": ref_number if ref_number else None,
            "description": description,
            "price": price,
            "selling_price": selling_price,
            "min_selling_price": min_selling_price,
            "quantity": quantity,
            "total_price": total_price,
            "date": today,
            "user": username,
            "barcode": f"barcodes/code_barres_{barcode_number}"
        }

        # Save order
        orders = []
        if os.path.exists(ORDERS_FILE):
            with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
                try:
                    orders = json.load(f)
                except json.JSONDecodeError:
                    pass

        orders.append(new_order)
        with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(orders, f, indent=2, ensure_ascii=False)

        # Update or add item
        found = False
        for item in items:
            if item.get('product_name') == product_name:
                item['quantity'] = item.get('quantity', 0) + quantity
                item['purchase_price'] = price
                item['selling_price'] = selling_price
                item['min_selling_price'] = min_selling_price
                item['description'] = description
                found = True
                break

        if not found:
            new_item = {
                "product_name": product_name,
                "barcode": barcode_number,
                "purchase_price": price,
                "selling_price": selling_price,
                "min_selling_price": min_selling_price,
                "quantity": quantity,
                "description": description,
                "seller": username,
                "date": today  # human-readable date format
            }
            items.append(new_item)

        with open(ITEMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

        flash('✅ Bestellung erfolgreich aufgegeben und Inventar aktualisiert!', 'success')
        return redirect(url_for('list_orders'))

    return render_template('order_item.html')


# Update Quantity
@app.route('/update_quantity', methods=['POST'])
@login_required('admin')  # oder 'seller' falls nötig
def update_quantity():
    barcode = request.form.get('barcode', '').strip()
    product_name = request.form.get('product_name', '').strip()
    add_quantity_str = request.form.get('add_quantity', '0').strip()

    # Flexible Barcode-Fallback:
    # Wenn kein barcode angegeben, aber product_name eine reine Zahl (Barcode) ist,
    # dann barcode = product_name, und product_name wird leer gesetzt
    if not barcode and product_name and product_name.isdigit():
        barcode = product_name
        product_name = ''

    # Menge validieren
    try:
        add_quantity = int(add_quantity_str)
        if add_quantity < 1:
            flash("Menge muss mindestens 1 sein.", "danger")
            return redirect(url_for('list_items'))
    except ValueError:
        flash("Ungültige Menge angegeben.", "danger")
        return redirect(url_for('list_items'))

    # Mindestens barcode oder product_name muss gesetzt sein
    if not barcode and not product_name:
        flash("Bitte Produktname oder Barcode eingeben.", "warning")
        return redirect(url_for('list_items'))

    # Items laden
    items = []
    if os.path.exists(ITEMS_FILE):
        with open(ITEMS_FILE, 'r', encoding='utf-8') as f:
            try:
                items = json.load(f)
            except json.JSONDecodeError:
                items = []

    found = False
    for item in items:
        # Nach Barcode exakt oder Produktname (case-insensitive) suchen
        if (barcode and item.get('barcode') == barcode) or (product_name and item.get('product_name', '').lower() == product_name.lower()):
            old_qty = item.get('quantity', 0)
            item['quantity'] = old_qty + add_quantity
            found = True
            flash(f"Menge von '{item.get('product_name')}' von {old_qty} auf {item['quantity']} erhöht.", "success")
            break

    if not found:
        flash("Produkt nicht gefunden. Bitte Produktname oder Barcode prüfen.", "warning")
        return redirect(url_for('list_items'))

    # Änderungen speichern
    with open(ITEMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    return redirect(url_for('list_items'))

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

@app.route('/orders')
@login_required(['admin', 'seller'])
def list_orders():
    role = session.get('role')
    username = session.get('username')
    all_orders = load_orders()
    users = list({o.get('user') for o in all_orders if o.get('user')})

    # Optional: filters from form
    filter_user = request.args.get('user', '')
    filter_date = request.args.get('date', '')

    # FILTER orders:
    if role == 'seller':
        # Show only orders created by the logged-in seller
        orders = [o for o in all_orders if o.get('user') == username]
    else:
        # Admin can see all
        orders = all_orders

    # Apply additional filter by user (only admins can filter this)
    if filter_user:
        orders = [o for o in orders if o.get('user') == filter_user]

    if filter_date:
        try:
            orders = [o for o in orders if o.get('date', '').startswith(filter_date)]
        except Exception:
            pass

    return render_template("list_orders.html", orders=orders, users=users)



def load_orders():
    try:
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_orders(orders):
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders, f, indent=4, ensure_ascii=False)

# Orders CRUD
# Edit Route
@app.route('/orders/edit/<order_number>', methods=['GET', 'POST'])

def edit_order(order_number):
    orders = load_orders()
    order = next((o for o in orders if o['order_number'] == order_number), None)
    if not order:
        flash("Bestellung nicht gefunden.", "danger")
        return redirect(url_for('list_orders'))

    if request.method == 'POST':
        try:
            order['product_name'] = request.form['product_name']
            order['ref_number'] = request.form['ref_number']
            order['price'] = float(request.form['price'])
            order['selling_price'] = float(request.form['selling_price'])
            order['min_selling_price'] = float(request.form['min_selling_price'])
            order['quantity'] = int(request.form['quantity'])
            order['description'] = request.form.get('description', '')
            order['photo'] = request.form.get('photo', '')
            order['total_price'] = order['selling_price'] * order['quantity']
            order['date'] = request.form['date']
            order['user'] = session.get('username', order.get('user', 'anonymous'))

            save_orders(orders)
            flash('Bestellung erfolgreich aktualisiert!', 'success')
            return redirect(url_for('list_orders'))
        except Exception as e:
            flash(f'Fehler beim Aktualisieren der Bestellung: {e}', 'danger')

    return render_template('edit_order.html', order=order)

# Orders CRUD
# Delete Route
@app.route('/orders/delete/<order_number>', methods=['POST'])
@login_required('admin')
def delete_order(order_number):
    orders = load_orders()
    # Find order with matching order_number
    order_to_delete = next((o for o in orders if o['order_number'] == order_number), None)
    if order_to_delete:
        orders.remove(order_to_delete)
        save_orders(orders)
        flash("Bestellung gelöscht.", "success")
    else:
        flash("Bestellung nicht gefunden.", "danger")
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
    sales_file = os.path.join('data', 'sales.json')
    purchases_file = os.path.join('data', 'orders.json')

    # Safely load all data
    def load_json(path):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        return []

    transactions = load_json(kasse_file)
    sales = load_json(sales_file)
    purchases = load_json(purchases_file)

    # Handle POST: Add or delete entry
    if request.method == 'POST':
        if 'delete_date' in request.form and session.get('role') == 'admin':
            delete_date = request.form['delete_date']
            transactions = [t for t in transactions if t['date'] != delete_date]
            with open(kasse_file, 'w', encoding='utf-8') as f:
                json.dump(transactions, f, indent=2, ensure_ascii=False)
            flash("Eintrag gelöscht.", "success")
            return redirect(url_for('kasse'))

        try:
            amount = float(request.form['betrag'])
            description = request.form.get('beschreibung', '').strip()
            ktype = request.form.get('typ', '').strip().lower()
            print("typ:", ktype, "amount before processing:", amount)
            if ktype not in ['einzahlung', 'auszahlung']:
                raise ValueError("Ungültiger Typ")

            # Auszahlung = negative amount
            amount = -abs(amount) if ktype == 'auszahlung' else abs(amount)
            print("amount after processing:", amount)
            
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

    # Balance calculations
    today = datetime.now().date()

    # Verkäufe heute
    total_sold_today = 0.0
    for sale in sales:
        try:
            sale_date = sale.get('date')
            if sale_date and datetime.fromisoformat(sale_date).date() == today:
                if isinstance(sale.get('items'), list):
                    total_sold_today += sum(item.get('total_price', 0) for item in sale['items'])
                else:
                    total_sold_today += sale.get('total_price', 0)
        except:
            continue

    # Bestellungen heute
    total_orders_today = 0.0
    for order in purchases:
        try:
            order_date = order.get('date')
            if order_date and datetime.fromisoformat(order_date).date() == today:
                total_orders_today += order.get('total_price', 0)
        except:
            continue

    # Gesamtsaldo
    current_balance = sum(t.get('amount', 0) for t in transactions)
    total_balance = current_balance + total_sold_today - total_orders_today

    return render_template(
        "kasse.html",
        transactions=reversed(transactions),  # newest first
        role=session.get('role'),
        current_balance=current_balance,
        total_sold_today=total_sold_today,
        total_orders_today=total_orders_today,
        total_balance=total_balance
    )


# Dimiss Alerts
@app.route('/dismiss_alert', methods=['POST'])
@login_required('admin')
def dismiss_alert():
    barcode = request.form.get('barcode')
    if not barcode:
        flash("⚠️ Ungültiger Barcode für Erinnerung.", "error")
        return redirect(url_for('seller_dashboard'))

    dismissed_alerts = load_json(ALERTS_DISMISS_FILE)

    now = datetime.now()
    remind_in_3_days = now + timedelta(days=3)

    existing = next((d for d in dismissed_alerts if d.get('barcode') == barcode), None)
    if existing:
        existing['remind_date'] = remind_in_3_days.isoformat()
    else:
        dismissed_alerts.append({
            "barcode": barcode,
            "remind_date": remind_in_3_days.isoformat()
        })

    save_json(ALERTS_DISMISS_FILE, dismissed_alerts)
    
    return redirect(url_for('admin_dashboard'))

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


