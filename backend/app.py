from flask import Flask, request, jsonify
from flask_bcrypt import Bcrypt
from flask_cors import CORS
import config  # For MongoDB URI configuration
from datetime import datetime, timedelta
import jwt
from functools import wraps
from bson import ObjectId  # Import ObjectId to convert the user_id for MongoDB query
import os
from pymongo import MongoClient
from bson.objectid import ObjectId

from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from flask_uploads import UploadSet, configure_uploads, IMAGES
app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)

# MongoDB connection
client = MongoClient(config.MONGO_URI)
db = client['user_db']
users = db['users']
content = db['content']

app.config['JWT_SECRET'] = 'mosin'
photos = UploadSet("photos", IMAGES)

db.users.create_index("email", unique=True)
db.users.create_index("username", unique=True)


UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)













# Decorator to check if the user is authenticated
def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"msg": "Token is missing!"}), 403
        try:
            token = token.split(" ")[1]  # Remove 'Bearer' prefix
            data = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
            current_user = users.find_one({"_id": ObjectId(data['user_id'])})
        except Exception as e:
            return jsonify({"msg": "Token is invalid!"}), 403
        return f(current_user, *args, **kwargs)
    return decorated_function




@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()

    # Validate required fields
    required_fields = ['username', 'email', 'password', 'mobile']
    for field in required_fields:
        if field not in data or not data[field].strip():
            return jsonify({"msg": f"{field} is required"}), 400

    # Check for existing username or email
    existing_user = users.find_one({"$or": [{"username": data['username']}, {"email": data['email']}]})

    if existing_user:
        return jsonify({"msg": "Username or email already exists"}), 400

    # Hash the password
    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')

    # Create the user object
    user = {
        "username": data['username'],
        "email": data['email'],
        "password": hashed_password,
        "mobile": data['mobile']
    }

    # Insert the user into the database
    try:
        users.insert_one(user)
        return jsonify({"msg": "User created successfully"}), 201
    except Exception as e:
        return jsonify({"msg": "Error creating user", "error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    # Get JSON data from the request
    data = request.get_json()

    # Check if the email or username exists in the database
    user = users.find_one({
        "$or": [
            {"email": data['email']},
            {"username": data['username']}
        ]
    })

    if user:
        # Check if the password matches (hashed password comparison)
        if bcrypt.check_password_hash(user['password'], data['password']):
            # Create a JWT token with the user's id (or any other info you want to include)
            token = jwt.encode(
                {"user_id": str(user['_id']), "exp": datetime.utcnow() + timedelta(hours=1)},  # expires in 1 hour
                config.JWT_SECRET,  # Secret key from your config
                algorithm="HS256"
            )
            print(token)
            return jsonify({"success": True, "msg": "Login successful", "token": token}), 200
        else:
            # Invalid password
            return jsonify({"success": False, "msg": "Invalid credentials"}), 401
    else:
        # User not found
        return jsonify({"success": False, "msg": "Invalid credentials"}), 401

@app.route('/user-info', methods=['GET'])
@token_required
def get_user_info(current_user):
    # Return user information
    if current_user:
        return jsonify({
            "user": {
                "username": current_user.get("username", ""),
                "email": current_user.get("email", ""),
                "mobile": current_user.get("mobile", ""),
                "bio": current_user.get("bio", ""),
                "website": current_user.get("website", ""),
                "gender": current_user.get("gender", ""),
                "fullName": current_user.get("fullName", ""),
            }
        }), 200
    return jsonify({"msg": "User not found!"}), 404

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Route to upload files
@app.route('/upload', methods=['POST'])
@token_required
def upload_file(current_user):
    if 'file' not in request.files:
        return jsonify({"msg": "No file part"}), 400
    file = request.files['file']
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)  # Now this should work
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Insert file information into the database
        file_data = {
            "user_id": current_user['_id'],
            "username": current_user['username'],
            "email": current_user['email'],
            "file_name": filename,
            "file_path": file_path,
            "file_type": "image" if filename.split('.')[-1].lower() in ['png', 'jpg', 'jpeg', 'gif'] else "pdf"
        }

        content.insert_one(file_data)

        return jsonify({"success": True, "msg": "File uploaded successfully"}), 200
    return jsonify({"msg": "Invalid file type"}), 400

# Route to get uploaded files
@app.route('/get-content', methods=['GET'])
@token_required
def get_content(current_user):
    files = content.find({"user_id": current_user['_id']})
    file_list = []
    for file in files:
        file_data = {
            "name": file["file_name"],
            "url": file["file_path"],
            "type": file["file_type"]
        }
        file_list.append(file_data)
    return jsonify({"files": file_list}), 200

@app.route('/update-profile', methods=['POST'])
def update_profile():
    try:
        # Get the data from the form
        username = request.form.get('username')
        full_name = request.form.get('fullName')
        website = request.form.get('website')
        bio = request.form.get('bio')
        email = request.form.get('email')
        phone = request.form.get('phone')
        gender = request.form.get('gender')
        
        print(username, full_name, website, bio, email, phone, gender)

        existing_user = users.find_one({"username": username})

        if not existing_user:
            return jsonify({"error": "User name is alrady taken."}), 404

        # Update the user's profile
        users.update_one(
            {"username": username},
            {
                "$set": {
                    "fullName": full_name,
                    "website": website,
                    "bio": bio,
                    "email": email,
                    "phone": phone,
                    "gender": gender
                }
            }
        )
        # Handle file upload (avatar)
        avatar = request.files.get('file')  # Get the uploaded file

        if avatar and allowed_file(avatar.filename):
            filename = secure_filename(avatar.filename)  # Secure the filename
            avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))  # Save the file


        return jsonify({"msg": "Profile updated successfully!"}), 200

    except Exception as e:
        print(f"Error: {e}")  # Log the error for debugging
        return jsonify({"error": "Failed to update profile."}), 500

if __name__ == '__main__':
    app.run(debug=True)
