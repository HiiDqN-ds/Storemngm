from flask import Flask, render_template, request, redirect, url_for, session, flash
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

# Decorators for login required
from functools import wraps
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                flash('Please login first', 'warning')
                return redirect(url_for('login'))
            if role and session.get('role') != role:
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


    
  
# Admin Dashboard
@app.route('/admin')
@login_required('admin')
def admin_dashboard():
    sales = load_sales()
    today = datetime.now().date()

    total_profit = sum(
        s.get('total_price', s.get('sale_price', 0) * s.get('quantity', 0))
        for s in sales
    )
    daily_profit = sum(
        s.get('total_price', s.get('sale_price', 0) * s.get('quantity', 0))
        for s in sales
        if datetime.fromisoformat(s['date']).date() == today
    )
    
    current_date = datetime.now().strftime('%d.%m.%Y')  # German date format

    return render_template('admin_dashboard.html',
                           sales=sales,
                           total_profit=total_profit,
                           daily_profit=daily_profit,
                           current_date=current_date)






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
        'name': next((i['name'] for i in items if i['barcode'] == barcode), barcode),
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

    # هنا نمرر seller وليس user أو users
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

# Admin: List Items to Edit
@app.route('/admin/items')
@login_required('admin')
def list_items():
    items = load_items()

    # Ensure default values for missing keys to avoid template errors
    for item in items:
        item['name'] = item.get('name', 'Unnamed Item')
        item['barcode'] = item.get('barcode', 'Unknown')
        item['purchase_price'] = float(item.get('purchase_price', 0.0))
        item['selling_price'] = float(item.get('selling_price', 0.0))
        item['min_selling_price'] = float(item.get('min_selling_price', 0.0))
        item['price'] = float(item.get('price', 0.0))
        item['quantity'] = int(item.get('quantity', 0))
        item['description'] = item.get('description', '')
        item['photo_link'] = item.get('photo_link', '')

    # Optional: Sort items alphabetically by name
    items.sort(key=lambda x: x['name'].lower())

    return render_template('items.html', items=items)


# Admin: List selled Items
@app.route('/admin/sales')
@login_required('admin')
def admin_sales():
    sales = load_sales()
    items = load_items()
    users = load_users()

    # Optional: enrich sales with item name and seller name for better display
    for sale in sales:
        sale['item_name'] = next((i['name'] for i in items if i['barcode'] == sale['barcode']), 'Unknown Item')
        sale['seller_name'] = sale.get('seller', 'Unknown')

    return render_template('admin_sales.html', sales=sales)

# Admin: Add Item
@app.route('/admin/items/add', methods=['GET', 'POST'])
@login_required('admin')
def add_item():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            barcode = request.form.get('barcode', '').strip()
            quantity = int(request.form.get('quantity', 0))
            photo_link = request.form.get('photo_link', '').strip()
            purchase_price = float(request.form.get('purchase_price', 0.0))
            selling_price = float(request.form.get('selling_price', 0.0))
            min_selling_price = float(request.form.get('min_selling_price', 0.0))
            description = request.form.get('description', '').strip()

            if not name or not barcode:
                flash('Name and Barcode are required.', 'danger')
                return redirect(url_for('add_item'))

            items = load_items()
            if any(item['barcode'] == barcode for item in items):
                flash('Barcode already exists.', 'danger')
                return redirect(url_for('add_item'))

            new_item = {
                'name': name,
                'barcode': barcode,
                'quantity': quantity,
                'image_url': photo_link,        # consistent naming
                'purchase_price': purchase_price,
                'selling_price': selling_price,          # key expected by templates
                'min_selling_price': min_selling_price,
                'description': description
            }


            items.append(new_item)
            save_items(items)
            flash('Item added successfully.', 'success')
            return redirect(url_for('list_items'))

        except ValueError:
            flash('Please enter valid numbers for prices and quantity.', 'danger')
            return redirect(url_for('add_item'))

    return render_template('add_item.html')



# Admin: Edit Item
@app.route('/admin/items/edit/<barcode>', methods=['GET','POST'])
@login_required('admin')
def edit_item(barcode):
    items = load_items()
    item = next((i for i in items if i['barcode'] == barcode), None)
    if not item:
        flash('Item not found', 'danger')
        return redirect(url_for('list_items'))

    if request.method == 'POST':
        item['name'] = request.form['name']
        item['price'] = float(request.form['price'])
        item['quantity'] = int(request.form['quantity'])
        item['photo_link'] = request.form.get('photo_link','')
        save_items(items)
        flash('Item updated', 'success')
        return redirect(url_for('list_items'))

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
    # Only allow 'admin' or 'seller' roles
    if 'username' not in session or session.get('role') not in ('admin', 'seller'):
        flash("❌ Zugriff verweigert. Bitte einloggen.", 'danger')
        return redirect(url_for('login'))

    items = load_items()

    if request.method == 'POST':
        barcode = request.form.get('barcode', '').strip()
        quantity_raw = request.form.get('quantity', '').strip()
        discount_active = request.form.get('discount_active')
        price_input = request.form.get('price', '').strip()

        # Validate barcode selection
        if not barcode:
            flash("❌ Bitte wählen Sie ein Produkt aus.", "danger")
            return redirect(url_for('sell_item'))

        # Find the item
        item = next((i for i in items if i.get('barcode') == barcode), None)
        if not item:
            flash('❌ Produkt nicht gefunden.', 'danger')
            return redirect(url_for('sell_item'))

        # Validate quantity
        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                raise ValueError()
        except ValueError:
            flash("❌ Bitte geben Sie eine gültige Menge größer als 0 ein.", "danger")
            return redirect(url_for('sell_item'))

        if quantity > item.get('quantity', 0):
            flash(f'❌ Nicht genug Bestand. Nur noch {item.get("quantity", 0)} verfügbar.', 'danger')
            return redirect(url_for('sell_item'))

        # Determine sale price
        if discount_active:
            try:
                sale_price = float(price_input)
                if sale_price <= 0:
                    raise ValueError()
            except ValueError:
                flash("❌ Bitte geben Sie einen gültigen Preis größer als 0 ein.", "danger")
                return redirect(url_for('sell_item'))
        else:
            # Use item's original price
            try:
                sale_price = float(item.get('price', 0))
                if sale_price <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                flash("❌ Das Produkt hat einen ungültigen Preis.", "danger")
                return redirect(url_for('sell_item'))

        # Update stock
        item['quantity'] -= quantity
        save_items(items)

        # Save the sale record
        sales = load_sales()
        sales.append({
            'seller': session['username'],
            'barcode': barcode,
            'quantity': quantity,
            'sale_price': sale_price,
            'total_price': round(sale_price * quantity, 2),
            'date': datetime.now().isoformat()
        })
        save_sales(sales)

        # Confirmation & warnings
        flash(f'✅ Verkauf von {quantity} × {item["name"]} erfolgreich.', 'success')
        if item['quantity'] <= 5:
            flash(f'⚠️ Achtung: Nur noch {item["quantity"]} Stück auf Lager!', 'warning')

        # Redirect depending on user role
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('seller_dashboard'))

    # GET request: render sell form with current items
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

    return render_template('seller_sales.html', sales=user_sales)


# Salary Payment
@app.route('/admin/pay-salary', methods=['GET', 'POST'])
@login_required('admin')
def pay_salary():
    users = load_users()  # تأكد أنه يرجع قائمة المستخدمين
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

        save_salary_payment(record)  # احفظ العملية حسب نظامك
        flash(f'تم دفع {amount} ل.س لـ {employee} من {source}', 'success')
        return redirect(url_for('pay_salary'))

    return render_template('pay_salary.html', users=users)


# Order
@app.route('/order', methods=['GET', 'POST'])
def order():
    if session.get('role') not in ['admin', 'seller']:
        flash('Zugriff verweigert.', 'danger')
        return redirect(url_for('index'))

    order_file = r'data/orders.json'
    numero_unique = None

    if request.method == 'POST':
        product_name = request.form['product_name']
        ref_number = request.form['ref_number']
        description = request.form['description']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        total_price = round(price * quantity, 2)

        today = datetime.now().strftime('%Y-%m-%d')
        username = session.get('username', 'unbekannt')

        numero_unique = ''.join([str(random.randint(0, 9)) for _ in range(12)])

        barcode_dir = os.path.join(app.static_folder, 'barcodes')
        os.makedirs(barcode_dir, exist_ok=True)
        barcode_path = os.path.join(barcode_dir, f'code_barres_{numero_unique}')
        code = barcode.get_barcode_class('ean13')(numero_unique, writer=ImageWriter())
        code.save(barcode_path)

        new_order = {
            "order_number": numero_unique,
            "product_name": product_name,
            "ref_number": ref_number,
            "description": description,
            "price": price,
            "quantity": quantity,
            "total_price": total_price,
            "date": today,
            "user": username,
            "barcode": f"barcodes/code_barres_{numero_unique}"
        }

        # Load and append order
        if os.path.exists(order_file):
            with open(order_file, 'r', encoding='utf-8') as f:
                try:
                    orders = json.load(f)
                except json.JSONDecodeError:
                    orders = []
        else:
            orders = []

        orders.append(new_order)

        with open(order_file, 'w', encoding='utf-8') as f:
            json.dump(orders, f, indent=2, ensure_ascii=False)

        flash('Bestellung erfolgreich aufgegeben!', 'success')
        return redirect(url_for('order'))

    return render_template('order_item.html', numero_unique=numero_unique)


def load_items_for_seller(username):
    all_items = load_items()
    return [item for item in all_items if item.get('seller') == username]

# List all the  items
# List all the items for the seller
@app.route('/seller/items')
@login_required('seller')
def seller_items():
    username = session['username']
    items = load_items_for_seller(username)  # Custom helper
    return render_template('seller_items.html', items=items)



import os
import json
from flask import render_template, request, redirect, url_for, session, flash

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

    return render_template('list_orders.html', orders=orders, users=unique_users)





# Orders CRUD
# Edit Route
# Edit Route
@app.route('/orders/edit/<int:index>', methods=['GET', 'POST'])
@login_required()
def edit_order(index):
    # Load orders using the defined path
    with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
        orders = json.load(f)

    if index >= len(orders):
        flash('Bestellung nicht gefunden.', 'danger')
        return redirect(url_for('list_orders'))

    order = orders[index]

    if request.method == 'POST':
        try:
            order['product_name'] = request.form['product_name']
            order['ref_number'] = request.form['ref_number']
            order['description'] = request.form['description']
            order['price'] = float(request.form['price'])
            order['quantity'] = int(request.form['quantity'])
            order['total_price'] = order['price'] * order['quantity']
            orders[index] = order

            with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(orders, f, indent=2, ensure_ascii=False)

            flash('Bestellung aktualisiert.', 'success')
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

    return render_template('list_salary_payments.html', payments=payments)



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


