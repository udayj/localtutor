from flask import Flask, request, render_template, Response, redirect, url_for,flash, jsonify
SECRET_KEY='SECRET'


SALT='123456789passwordsalt'

app = Flask(__name__)
app.debug=True

@app.route('/')
def main_page():
	return render_template('main_page.html')

if __name__ == "__main__":
    app.run()