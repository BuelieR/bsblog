from flask import Flask, render_template, request, redirect, url_for, flash, session
from waitress import serve
import os
import json
import uuid
import hashlib
import markdown

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# 管理员默认密码
ADMIN_PASSWORD = hashlib.sha512('1366yyds'.encode('utf-8')).hexdigest()

# 确保文件存在，如果不存在则创建
def ensure_file_exists(file_path, content={}):
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(content, file, ensure_ascii=False, indent=4)

# 加载用户数据
def load_users():
    ensure_file_exists('data/users.json')
    with open('data/users.json', 'r', encoding='utf-8') as file:
        return json.load(file)

# 保存用户数据
def save_users(users):
    with open('data/users.json', 'w', encoding='utf-8') as file:
        json.dump(users, file, ensure_ascii=False, indent=4)

# 加密密码
def encrypt_password(password):
    return hashlib.sha512(password.encode('utf-8')).hexdigest()

# 初始化管理员用户
def initialize_admin():
    users = load_users()
    if 'admin' not in users:
        users['admin'] = {'username': 'admin', 'password': ADMIN_PASSWORD}
        save_users(users)

# 确保所有文章都有 id
def ensure_posts_have_ids():
    posts = load_posts()
    modified = False
    for post in posts:
        if 'id' not in post:
            post['id'] = str(uuid.uuid4())
            modified = True
    if modified:
        save_posts(posts)

# 检查用户是否登录
def is_logged_in():
    return 'user_id' in session and session['user_id'] is not None

# 检查用户是否是管理员
def is_admin():
    return is_logged_in() and session['user_id'] == 'admin'

# 注册自定义函数到Jinja2环境
app.jinja_env.globals.update(is_logged_in=is_logged_in)
app.jinja_env.globals.update(is_admin=is_admin)

# 加载文章数据
def load_posts():
    ensure_file_exists('data/posts.json')
    with open('data/posts.json', 'r', encoding='utf-8') as file:
        return json.load(file)

# 保存文章数据
def save_posts(posts):
    with open('data/posts.json', 'w', encoding='utf-8') as file:
        json.dump(posts, file, ensure_ascii=False, indent=4)

# 主页
@app.route('/')
def index():
    ensure_posts_have_ids()  # 确保所有文章都有 id
    posts = load_posts()
    approved_posts = [post for post in posts if post['approved'] or is_admin()]
    users = load_users()
    for post in approved_posts:
        post['author'] = users.get(post['author_id'], {}).get('username', '未知作者')
        post['content_html'] = markdown.markdown(post['content'], extensions=['markdown.extensions.extra', 'markdown.extensions.tables', 'markdown.extensions.fenced_code'])
    return render_template('index.html', posts=approved_posts)

# 登录页面
@app.route('/login', methods=['GET', 'POST'])
def login():
    users = load_users()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        encrypted_password = encrypt_password(password)
        for user_id, user_info in users.items():
            if user_info['username'] == username and user_info['password'] == encrypted_password:
                session['user_id'] = user_id
                flash('登录成功！', 'success')
                if user_id == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('index'))
        flash('用户名或密码错误！', 'danger')
    return render_template('login.html')

# 注册页面
@app.route('/register', methods=['GET', 'POST'])
def register():
    users = load_users()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if len(password) < 8 or len(password) > 16:
            flash('密码长度必须在8到16位之间！', 'danger')
        elif any(user_info['password'] == encrypt_password(password) for user_info in users.values()):
            flash('密码已被使用，请选择其他密码！', 'danger')
        else:
            new_user_id = str(uuid.uuid4())
            users[new_user_id] = {'username': username, 'password': encrypt_password(password)}
            save_users(users)
            flash('注册成功！', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

# 退出登录
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('已退出登录！', 'success')
    return redirect(url_for('index'))

# 发表新文章
@app.route('/add', methods=['GET', 'POST'])
def add_post():
    if not is_logged_in():
        flash('请先登录！', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category = request.form['category']
        user_id = session['user_id']
        posts = load_posts()
        new_post_id = str(uuid.uuid4())  # 生成唯一的id
        posts.append({'id': new_post_id, 'title': title, 'content': content, 'approved': False, 'author_id': user_id, 'category': category})
        save_posts(posts)
        flash('文章已提交待审！', 'success')
        return redirect(url_for('user_dashboard'))
    return render_template('edit_post.html')

# 编辑文章
@app.route('/edit/<string:post_id>', methods=['GET', 'POST'])  # 修改为 string
def edit_post(post_id):
    if not is_logged_in():
        flash('请先登录！', 'danger')
        return redirect(url_for('login'))

    posts = load_posts()
    post = next((p for p in posts if p['id'] == post_id), None)
    post_index = next((i for i, p in enumerate(posts) if p['id'] == post_id), None)
    if post_index is None:
        flash('文章不存在！', 'danger')
        return redirect(url_for('user_dashboard'))

    if post['author_id'] != session['user_id'] and not is_admin():
        flash('您没有权限编辑这篇文章！', 'danger')
        return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category = request.form['category']
        posts[post_index]['title'] = title
        posts[post_index]['content'] = content
        posts[post_index]['category'] = category
        save_posts(posts)
        flash('文章已更新！', 'success')
        if is_admin():
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return render_template('edit_post.html', post=post, post_id=post_id)

# 删除文章
@app.route('/delete/<string:post_id>')  # 修改为 string
def delete_post(post_id):
    if not is_logged_in():
        flash('请先登录！', 'danger')
        return redirect(url_for('login'))

    posts = load_posts()
    post_index = next((i for i, p in enumerate(posts) if p['id'] == post_id), None)
    if post_index is None:
        flash('文章不存在！', 'danger')
        return redirect(url_for('user_dashboard'))

    if posts[post_index]['author_id'] != session['user_id'] and not is_admin():
        flash('您没有权限删除这篇文章！', 'danger')
        return redirect(url_for('user_dashboard'))

    del posts[post_index]
    save_posts(posts)
    flash('文章已删除！', 'success')
    if is_admin():
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('user_dashboard'))

# 审核文章
@app.route('/approve/<string:post_id>')  # 修改为 string
def approve_post(post_id):
    if not is_admin():
        flash('只有管理员才能访问此页面！', 'danger')
        return redirect(url_for('login'))

    posts = load_posts()
    post_index = next((i for i, p in enumerate(posts) if p['id'] == post_id), None)
    if post_index is None:
        flash('文章不存在！', 'danger')
        return redirect(url_for('admin_dashboard'))

    posts[post_index]['approved'] = True
    save_posts(posts)
    flash('文章已审核通过！', 'success')
    return redirect(url_for('admin_dashboard'))

# 文章详情页
@app.route('/post/<string:post_id>')  # 修改为 string
def post(post_id):
    if not is_logged_in():
        flash('请先登录！', 'danger')
        return redirect(url_for('login'))

    posts = load_posts()
    selected_post = next((p for p in posts if p['id'] == post_id), None)
    if selected_post is None:
        flash('文章不存在！', 'danger')
        return redirect(url_for('index'))

    users = load_users()
    selected_post['author'] = users.get(selected_post['author_id'], {}).get('username', '未知作者')
    selected_post['content_html'] = markdown.markdown(selected_post['content'], extensions=['markdown.extensions.extra', 'markdown.extensions.tables', 'markdown.extensions.fenced_code'])
    return render_template('post.html', post=selected_post, post_id=selected_post['id'])

# 用户仪表盘
@app.route('/user_dashboard')
def user_dashboard():
    ensure_posts_have_ids()  # 确保所有文章都有 id
    if not is_logged_in():
        flash('请先登录！', 'danger')
        return redirect(url_for('login'))

    user_id = session['user_id']
    posts = load_posts()
    user_posts = [post for post in posts if post.get('author_id') == user_id]
    users = load_users()
    for post in user_posts:
        post['author'] = users.get(post['author_id'], {}).get('username', '未知作者')
    return render_template('user_dashboard.html', posts=user_posts)

# 管理员仪表盘
@app.route('/admin_dashboard')
def admin_dashboard():
    ensure_posts_have_ids()  # 确保所有文章都有 id
    if not is_admin():
        flash('只有管理员才能访问此页面！', 'danger')
        return redirect(url_for('login'))

    posts = load_posts()
    pending_posts = [post for post in posts if not post['approved']]
    approved_posts = [post for post in posts if post['approved']]
    users = load_users()
    for post in pending_posts:
        post['author'] = users.get(post['author_id'], {}).get('username', '未知作者')
    for post in approved_posts:
        post['author'] = users.get(post['author_id'], {}).get('username', '未知作者')
    return render_template('admin_dashboard.html', pending_posts=pending_posts, approved_posts=approved_posts)

if __name__ == '__main__':
    # 初始化管理员用户
    initialize_admin()
    # 确保所有文章都有 id
    ensure_posts_have_ids()
    # 使用 Waitress 作为 WSGI 服务器
    #app.run(debug=True)
    serve(app, host='0.0.0.0', port=8080)