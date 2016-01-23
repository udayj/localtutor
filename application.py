from flask import Flask, request, render_template, Response, redirect, url_for,flash, jsonify
from pymongo import MongoClient
from flask.ext.login import (LoginManager, current_user, login_required,
                            login_user, logout_user, UserMixin, confirm_login,
                             fresh_login_required,login_url)
from bson.objectid import ObjectId
import re
import json
from datetime import datetime,timedelta
import codecs
import os
from itsdangerous import URLSafeTimedSerializer
import operator
import nltk
import pycrfsuite
import math
import requests
import hashlib
import multiprocessing
from pytz import timezone
from datetime import datetime




SECRET_KEY='SECRET'


SALT='123456789passwordsalt'

app = Flask(__name__)
app.config.from_envvar('CONFIG')

app.debug=True
app.secret_key=SECRET_KEY


REMEMBER_COOKIE_DURATION=timedelta(days=365)
app_id=app.config['FACEBOOK_APP_ID']
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = u"Please log in to access this page."

login_serializer = URLSafeTimedSerializer(SECRET_KEY)

def set_subject_area():
	client=MongoClient()
	db=client.local_tutor
	subjects_db=db.subjects.find()
	teachers=db.teachers.find()
	subjects=[]
	areas=[]
	for subject in subjects_db:
		if len(subject['name'].strip())>1 and subject['name'] not in subjects:
			subjects.append(subject['name'])
	for teacher in teachers:
		if teacher['area'] not in areas and len(teacher['area'].strip())>1:
			areas.append(teacher['area'])
	return (subjects,areas)

def npchunk_features(sentence, i, history='O'):

	client=MongoClient()
	db=client.local_tutor
	subjects, areas = set_subject_area()

	word = sentence[i]
	if i==0:
		prevword = 'START'
	else:
		prevword = sentence[i-1]

	if i<2:
		prevword_more= 'START'
	else:
		prevword_more= sentence[i-2]

	if i>=len(sentence)-2:
		lookahead='END'
	else:
		lookahead = sentence[i+2]

	if i==len(sentence)-1:
		nextword = 'END'
		
	else:
		nextword = sentence[i+1]

	


	features = ['word='+word,
				#'prev_words='+str((prevword,prevword_more)),
				#'next_words='+str((nextword,lookahead)),
				#'prev_class='+history,
				'w_pw='+prevword+word,
				'w_nw='+word+nextword
				#'w_prev_class='+word+history

				]
	
	is_gazette='n'
	if word in subjects or word in areas:
		is_gazette='y'
	word_prev_bigram=prevword+' '+word
	p_bigram_gazette='n'
	if prevword!='START':
		if word_prev_bigram in subjects or word_prev_bigram in areas:
			p_bigram_gazette='y'
	word_next_bigram=word+' '+nextword
	n_bigram_gazette='n'
	if nextword !='END':
		if word_next_bigram in subjects or word_next_bigram in areas:
			n_bigram_gazette='y'

	p_trigram_gazette='n'
	p_trigram=prevword_more+' '+prevword+' '+word
	if p_trigram in subjects or p_trigram in areas:
		p_trigram_gazette='y'
	n_trigram_gazette='n'
	n_trigram=word+' '+nextword+' '+lookahead
	if n_trigram in subjects or n_trigram in areas:
		n_trigram_gazette='y'



	features.append('is_gazette='+is_gazette)
	features.append('w_is_gazette='+word+'_'+is_gazette)
	features.append('p_bigram_gazette='+p_bigram_gazette)
	features.append('n_bigram_gazette='+n_bigram_gazette)
	features.append('w_pw_ppw='+prevword_more+' '+prevword+' '+word)
	features.append('w_nw_nnw='+word+' '+nextword+' '+lookahead)
	features.append('p_trigram_gazette='+p_trigram_gazette)
	features.append('n_trigram_gazette='+n_trigram_gazette)
	return features


class User(UserMixin):
    def __init__(self, name, _id, fb_id=None,password=None,email=None,activation_hash=None,active=True,user_type='user'):
        self.name = name
        self.id = _id
        self.fb_id=fb_id
        self.active=active
        self.password=password
        self.email=email
        self.activation_hash=activation_hash
        self.user_type=user_type
    
    def is_active(self):
        return self.active
        
    
    def get_auth_token(self):
        """
        Encode a secure token for cookie
        """
        data = [str(self.id)]
        return login_serializer.dumps(data)

@login_manager.user_loader
def load_user(_id):

	app.logger.debug("in load_user")
	client=MongoClient()
	db=client.local_tutor
	user=db.users.find({'_id':ObjectId(_id)})
	try:
		user=user.next()
		if 'fb_id' in user and user['fb_id']!=None:
			ret_user=User(name=user['name'],fb_id=user['fb_id'],_id=str(user['_id']),active=True)
		else:
			if 'user_type' in user and user['user_type']=='tutor':
				ret_user=User(name=user['name'],_id=str(user['_id']),active=True,user_type=user['user_type'])	
			else:
				ret_user=User(name=user['name'],_id=str(user['_id']),active=True)
		return ret_user
	except StopIteration:
		return None

@app.route('/activate')
def activate():
	activation_hash=request.args.get('hash')
	if not activation_hash:
		return render_template('activate_error.html')
	client=MongoClient()
	db=client[app.config['DATABASE']]
	user=db.users.find({'activation_hash':activation_hash})
	
	try:
		user=user.next()
		user_active=False
		user_active=user['active']
		user['active']=True
		db.users.save(user)
		ret_user=User(name=user['name'],email=user['email'],password="",active=user['active'],_id=str(user['_id']))
		

		
		if 'user_type' in user and user['user_type']=='tutor':
			if 'tutor_id' not in user:
				fields=['subject','name','contact_number','email','age_group','venue',
				'classroom_type','geographical_location','area','usp','teacher_type','price']
				teacher_structured={}
				for field in fields:
					teacher_structured[field]=''
				teacher_structured['name']=user['name']
				teacher_structured['email']=user['email']
				teacher_structured['contact_number']=[user['phone']]
				_id=db.teachers.save(teacher_structured)
				user['tutor_id']=str(_id)
				db.users.save(user)
			return render_template('activate_tutor.html')	

		login_user(ret_user)
		return render_template('activate.html')
	except StopIteration:
		return render_template('activate_error.html')



@login_manager.token_loader
def load_token(token):
    """
    Flask-Login token_loader callback. 
    The token_loader function asks this function to take the token that was 
    stored on the users computer process it to check if its valid and then 
    return a User Object if its valid or None if its not valid.
    """
    app.logger.debug("in load_token")
    #The Token itself was generated by User.get_auth_token.  So it is up to 
    #us to known the format of the token data itself.  
 
    #The Token was encrypted using itsdangerous.URLSafeTimedSerializer which 
    #allows us to have a max_age on the token itself.  When the cookie is stored
    #on the users computer it also has a exipry date, but could be changed by
    #the user, so this feature allows us to enforce the exipry date of the token
    #server side and not rely on the users cookie to exipre. 
    max_age = REMEMBER_COOKIE_DURATION.total_seconds()
 
    #Decrypt the Security Token, data = [username, hashpass]
    data = login_serializer.loads(token, max_age=max_age)
 
    #Find the User
    user = load_user(data[0])
 
    #Check Password and return user or None
    if user:
        return user
    return None

login_manager.init_app(app)

def content_entry(file_name,db_name):
	f=codecs.open(file_name,'r','utf-8')
	client=MongoClient()
	db=client[db_name]
	count=0
	try:
		while True:
			teacher=f.readline()
			
			if not teacher:
				break
			teacher_parts=teacher.split('\t')
			
			if len(teacher_parts)<12:
				continue
			teacher_structured={}

			fields=['subject','name','contact_number','email','age_group','venue',
			'classroom_type','geographical_location','area','usp','teacher_type','price']
			counter=0
			
			good_value=True
			for field in fields:

				if counter==0 or counter==1:
					teacher_part=teacher_parts[counter].lower().strip()
					if len(teacher_part)<1:
						good_value=False
						break
				if counter==0:
					parts=teacher_parts[counter].lower().strip().split(',')
					subjects=[part.lower().strip() for part in parts]
					teacher_structured[field]=subjects
					for subject in subjects:
						prior_subject_count=db.subjects.find({'name':subject}).count()
						if prior_subject_count<=0:
							db.subjects.save({'name':subject,'category':''})

				elif counter==2:
					parts=teacher_parts[counter].lower().strip().split(',')
					teacher_structured[field]=[part.lower().strip() for part in parts]
				else:	
					teacher_structured[field]=teacher_parts[counter].lower().strip()
					
				counter=counter+1
			
			if good_value==True:
				count=count+1
				db.teachers.save(teacher_structured)
	except Exception as e:
		print (e)
		return -100
	
	return count


@app.route('/')
def main_page():
	title='- Find tutors and courses for anything you want to learn from over 800 subjects and 10000 teachers'
	meta_description='Find tutors/teachers and courses for anything you want to learn from over 800 subjects and 10000 teachers'
	return render_template('main_page.html',app_id=app_id,active='main',title=title,meta_description=meta_description)

@app.route('/user_profile')
def user_profile():
	user_id=request.args.get('id')
	
	
	if not user_id or user_id=='':
		return render_template('error.html')

	
	client=MongoClient()
	db=client.local_tutor
	user=db.users.find({'_id':ObjectId(user_id)})
	try:
		user=user.next()
		if 'user_type' in user and user['user_type']=='tutor' and hasattr(current_user,'id') and current_user.id==user_id:
			if 'tutor_id' not in user:
				raise Exception
			tutor_id=user['tutor_id']
			tutor=db.teachers.find({'_id':ObjectId(tutor_id)})
			tutor=tutor.next()
			return render_template('tutor_profile.html',tutor=tutor)

		if 'user_type' in user and user['user_type']=='tutor':

			return redirect('/tutor?id='+user['tutor_id'])


		name=user['name']
		age=''
		school=''
		wish_list=''
		favorite=''

		if 'age' in user:
			age=user['age']
		if 'school' in user:
			school=user['school']
		if 'wish_list' in user:
			wish_list=user['wish_list']
		if 'favorite' in user:
			favorite=user['favorite']
		
		if hasattr(current_user,'id') and current_user.id==user_id:
			return render_template('user_profile.html',name=name,age=age,
				school=school, wish_list=','.join(wish_list),favorite=favorite,app_id=app_id)
		else:

			return render_template('user_profile_readonly.html',name=name,
				school=school, wish_list=wish_list,favorite=favorite,app_id=app_id)

	except Exception as e:
		app.logger.error(str(e))
		return render_template('error.html')

@login_required
@app.route('/save_user_data',methods=['POST'])
def save_user_data():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))
	_id=current_user.id
	client=MongoClient()
	db=client.local_tutor
	user=db.users.find({'_id':ObjectId(_id)})
	try:
		user=user.next()
		if 'age' not in data or 'school' not in data or 'wish_list' not in data or 'favorite' not in data:
			js=json.dumps({'result':'failed'})
			resp=Response(js,status=200,mimetype='application/json')
			return resp
		user['age']=data['age']
		user['school']=data['school']
		user['wish_list']=data['wish_list'].split(',')
		user['favorite']=data['favorite']
		db.users.save(user)
		print 'saved user data'
		js=json.dumps({'result':'success'})
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	except:
		print 'problem with user data'
		js=json.dumps({'result':'failed'})
		resp=Response(js,status=200,mimetype='application/json')
		return resp

@app.route('/get_friends',methods=['POST'])
def get_friends():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=[element.strip() for element in value]
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'friends[]' not in data:
		response={}
		response={'result':'success'}
		response['friends']=[]
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	friends=data['friends[]']
	result=[]
	for friend in friends:
		user=db.users.find({'fb_id':friend})
		try:
			user=user.next()
			actual_user={}
			actual_user['_id']=str(user['_id'])
			actual_user['fb_id']=user['fb_id']
			result.append(actual_user)
		except:
			pass
	
	print result
	response={}
	response={'result':'success'}
	response['friends']=result
	js=json.dumps(response)
	print response
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@app.route('/login',methods=['POST'])
def login():

	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))

	client=MongoClient()
	db=client.local_tutor
	if 'fb_user_id' not in data or 'fb_user_name' not in data or 'redirect_url' not in data:
		return render_template('error.html')
	user=db.users.find({'fb_id':data['fb_user_id']})
	try:
		user=user.next()
		ret_user=User(name=user['name'],_id=str(user['_id']),fb_id=user['fb_id'])
		app.logger.debug(ret_user.name)
		app.logger.debug(ret_user.id)
		app.logger.debug(ret_user.fb_id)
		app.logger.debug(ret_user.active)

		
		if login_user(ret_user,force=True):
			if 'redirect_url' in data and data['redirect_url'][-6:]!='login2':
				return redirect(data['redirect_url'])
			else:
				return redirect('/user_profile?id='+ret_user.id)
		else:
			return render_template('error.html')
	except StopIteration:
		user={}
		user['fb_id']=data['fb_user_id']
		user['name']=data['fb_user_name']
		_id=db.users.save(user)
		ret_user=User(name=user['name'],_id=_id,fb_id=user['fb_id'])
		
		if login_user(ret_user, force=True):
			if 'redirect_url' in data:
				return redirect('/user_profile?id='+ret_user.id)
			else:	
				return redirect('/user_profile?id='+ret_user.id)
		else:
			return render_template('error.html')

@app.route('/signup',methods=['GET','POST'])
def signup():
	def send_mail(data,files):
		result=requests.post(
        "https://api.mailgun.net/v2/tutorack.com/messages",
        auth=("api", "key-1b9979216cd5d2f065997d3d53852cd6"),
        files=files,
        data=data)

	if request.method=='GET':
		return render_template('signup.html',active='signup',app_id=app_id)
	else:
		
		data={}
		for name,value in dict(request.form).iteritems():
			data[name]=value[0]
		username=None
		if 'username' in data:
			username=data['username']
		client=MongoClient()
		db=client[app.config['DATABASE']]
		salt='tutorackactivateusingtoken'
		activation_hash=hashlib.sha512(salt+data['email']).hexdigest()[10:30]
		
		exist_user=db.users.find({'email':data['email']})
		try:
			exist_user.next()
			return render_template('signup.html',active='signup',signup_error='Email already exists',username=username,email=data['email'],app_id=app_id)
		except StopIteration:
			pass

		_id=db.users.save({'name':username,
					   'email':data['email'],
					   'password':hashlib.sha512(SALT+data['password']).hexdigest(),
					   'activation_hash':activation_hash,
					   'active':False})
		#user=User(name=username,email=data['email'],password=data['password'],active=False,id=str(_id))
		
		app.logger.debug('Sending activation email to:'+data['email'])
		html_content=render_template("activate_email.html",name=username, url=app.config['HOST']+'/activate?hash='+activation_hash)
		data={"from": "Tutorack <admin@tutorack.com>",
              "to": [data['email']],
              "subject": 'Welcome to Tutorack',
              "text": 'Click this link to activate your account '+app.config['HOST']+'/activate?hash='+activation_hash,
              "html":html_content}
		#app.logger.debug(activation_hash)
		#app.logger.debug(str(app.extensions['mail'].server))
		try:
			p=multiprocessing.Process(target=send_mail,args=(data,None,))
			p.start()
		except Exception:
			db.users.remove({'_id':_id})
			return render_template('signup.html',signup_error='Problem sending email. Account not created. Try again later.',
									username=username,email=data['email'],app_id=app_id)
		return render_template('checkmail.html',app_id=app_id)

@app.route('/signup_tutor',methods=['GET','POST'])
def signup_tutor():
	def send_mail(data,files):
		result=requests.post(
        "https://api.mailgun.net/v2/tutorack.com/messages",
        auth=("api", "key-1b9979216cd5d2f065997d3d53852cd6"),
        files=files,
        data=data)

	if request.method=='GET':
		return render_template('signup_tutor.html',app_id=app_id)
	else:
		
		data={}
		for name,value in dict(request.form).iteritems():
			data[name]=value[0]
		username=None
		if 'username' in data:
			username=data['username']
		if 'username' not in data or 'password' not in data or 'email' not in data or 'phone' not in data:
			return render_template('signup_tutor.html',active='signup',signup_error='Incomplete data submitted',username=username,email=data['email'],app_id=app_id)
		client=MongoClient()
		db=client[app.config['DATABASE']]
		salt='tutorackactivateusingtoken'
		activation_hash=hashlib.sha512(salt+data['email']).hexdigest()[10:30]
		
		exist_user=db.users.find({'email':data['email']})
		try:
			exist_user.next()
			return render_template('signup_tutor.html',active='signup',signup_error='Email already exists',username=username,email=data['email'],app_id=app_id)
		except StopIteration:
			pass

		_id=db.users.save({'name':username,
					   'email':data['email'],
					   'password':hashlib.sha512(SALT+data['password']).hexdigest(),
					   'activation_hash':activation_hash,
					   'user_type':'tutor',
					   'phone':data['phone'],
					   'active':False})
		#user=User(name=username,email=data['email'],password=data['password'],active=False,id=str(_id))
		
		app.logger.debug('Sending activation email to:registrations@tutorack.com')
		html_content=render_template("activate_email_tutor.html",name=username, email=data['email'],phone=data['phone'],
									url=app.config['HOST']+'/activate?hash='+activation_hash)

		data={"from": "Tutorack <admin@tutorack.com>",
              "to": 'registrations@tutorack.com',
              "subject": 'New Tutor Registration',
              "text": 'Click this link to activate new tutor account '+app.config['HOST']+'/activate?hash='+activation_hash,
              "html":html_content}
		#app.logger.debug(activation_hash)
		#app.logger.debug(str(app.extensions['mail'].server))
		try:
			p=multiprocessing.Process(target=send_mail,args=(data,None,))
			p.start()
		except Exception:
			db.users.remove({'_id':_id})
			return render_template('signup_tutor.html',signup_error='Problem processing request. Account not created. Pls try again later.',
									username=username,email=data['email'],app_id=app_id)
		return redirect('/activate?hash='+activation_hash)

@app.route('/change-password',methods=['GET','POST'])
def change_password():
	def send_mail(data,files):
		result=requests.post(
        "https://api.mailgun.net/v2/remindica.com/messages",
        auth=("api", "key-1b9979216cd5d2f065997d3d53852cd6"),
        files=files,
        data=data)
	if request.method=='GET':
		forgot_password_hash=request.args.get('hash')
		client=MongoClient()
		db=client[app.config['DATABASE']]
		if not forgot_password_hash:
			return render_template('change-password.html',error="Incorrect password reset link")
		user=db.users.find({'forgot_password_hash':forgot_password_hash})
		try:
			user=user.next()
			if 'forgot_password' in user and user['forgot_password']==True:
				return render_template('change-password.html',email=user['email'])
			else:
				return render_template('change-password.html',
					error="Password already changed using this link - please request another password reset",email=user['email'])
		except StopIteration:
			return render_template('change-password.html',error='Problem with this link - please contact support@remindica.com')

	else:
		data={}
		for name,value in dict(request.form).iteritems():
			data[name]=value[0]
		client=MongoClient()
		db=client[app.config['DATABASE']]
		
		email=None
		if 'email' in data and 'password' in data:
			email=data['email']
			password=data['password']
		else:
			app.logger.debug('Change password form submitted without email/password')
			return render_template('change-password.html',error="Please re-enter details to reset password")

		user=db.users.find({'email':email})
		
		try:
			user=user.next()
			if user['forgot_password']!=True:
				return render_template('change-password.html',error='Please request another password reset link')	
			user['password']=hashlib.sha512(SALT+password).hexdigest()
			user['forgot_password']=False
			db.users.save(user)
			return render_template('change-password.html',success='Password changed successfully')
		except StopIteration:
			return render_template('change-password.html',error='Please request another password reset link')


@app.route('/forgot-password',methods=['GET','POST'])
def forgot_password():
	def send_mail(data,files):
		result=requests.post(
        "https://api.mailgun.net/v2/tutorack.com/messages",
        auth=("api", "key-1b9979216cd5d2f065997d3d53852cd6"),
        files=files,
        data=data)
	if request.method=='GET':
		return render_template('forgot-password.html')
	else:
		data={}
		for name,value in dict(request.form).iteritems():
			data[name]=value[0]
		client=MongoClient()
		db=client[app.config['DATABASE']]
		salt='tutorackforgotpassword'
		email=None
		if 'email' in data:
			email=data['email']
		else:
			app.logger.debug('Forgot password form submitted without email')
			return render_template('forgot-password.html',error="Please enter correct email id to reset password")	

		user=db.users.find({'email':email})
		forgot_password_hash=hashlib.sha512(salt+data['email']).hexdigest()[10:30]
		try:
			user=user.next()
			user['forgot_password_hash']=forgot_password_hash
			user['forgot_password']=True
			db.users.save(user)
			html_content=render_template("forgot_password_email.html",url=app.config['HOST']+'/change-password?hash='+forgot_password_hash)
			data={"from": "Tutorack <support@tutorack.com>",
	              "to": email,
	              "subject": 'Reset your password',
	              "text": 'Click this link to change your password '+app.config['HOST']+'/change-password?hash='+forgot_password_hash,
	              "html":html_content}
			try:
				p=multiprocessing.Process(target=send_mail,args=(data,None,))
				p.start()
				
				return render_template('forgot-password.html',success="Password reset instructions sent to your email id")
			except:
				return render_template('forgot-password.html',error="Could not send password reset instructions - please try again")
		except StopIteration:
			return render_template('forgot-password.html',error="Please enter correct email id to reset password")			



@app.route('/login2',methods=['GET','POST'])
def login2():
	
	
	if request.method=='GET':
		return render_template('login2.html',active='login2',app_id=app_id)
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0]
	
	username=None
	if 'username' in data and 'password' in data:
		username=data['username']
		password=data['password']
	else:
		app.logger.debug('Login Form submitted without fields')
		return render_template('login2.html',active='login2',app_id=app_id)
	remember_me=False
	if 'remember_me' in data:
		if data['remember_me']=='on':
			remember_me=True
	
	client=MongoClient()
	db=client[app.config['DATABASE']]
	password=hashlib.sha512(SALT+password).hexdigest()
	user=db.users.find({'email':username,'password':password})
	try:
		user=user.next()
		if 'user_type' in user and user['user_type']=='tutor':
			print 'user_type:tutor'
			ret_user=User(name=user['name'],email=user['email'],
			password=user['password'],active=user['active'],_id=str(user['_id']),user_type=user['user_type'])
		else:		
			ret_user=User(name=user['name'],email=user['email'],password=user['password'],active=user['active'],_id=str(user['_id']))
		if login_user(ret_user,remember=remember_me):
			app.logger.error('checking  '+current_user.user_type)
			flash('Logged in!')
			if 'redirect_url' in data:
				return redirect(data['redirect_url'])
			else:		
				return redirect('/user_profile?id='+ret_user.id)
		else:
			return render_template('login2.html',error='Cannot login. Account still inactive',active='login2',app_id=app_id)
	except StopIteration:
		return render_template('login2.html',error='Cannot login. Wrong credentials',
								active='login2',app_id=app_id)

	
@app.route('/logout')
def logout():
	logout_user()
	flash("Logged out!")
	redirect_url=request.args.get('redirect_url')
	if redirect_url is not None:
		return redirect(redirect_url)
	return redirect('/')

@app.route('/tutor_registration',methods=['GET','POST'])
def tutor_registration():
	client=MongoClient()
	db=client.local_tutor
	tutors=db.users.find({'user_type':'tutor'})
	return render_template('tutor_registration.html',tutors=tutors)


def rewrite_query(query):
	client=MongoClient()
	db=client.local_tutor
	query=query.lower()
	category_count=db.subjects.find({'category':query}).count()
	if category_count<=0:
		return [query]
	subjects=db.subjects.find({'category':query})
	output=[]
	for subject in subjects:
		output.append(subject['name'])
	
	subjects=db.subjects.find({'name':query})
	for subject in subjects:
		output.append(subject['name'])
	output.append(query)
	return output

@app.route('/upload')
def upload():
	return render_template('upload.html')

@app.route('/upload_staging',methods=['POST'])
def upload_staging():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))

	if 'password' not in data:
		js=json.dumps({'result':'failed','message':'Cannot authenticate'})
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	if data['password']!='uploadtutorack':
		js=json.dumps({'result':'failed','message':'Cannot authenticate'})
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	attachment=request.files['attachment']
	#save file -> call routine with that file name for staging db -> if no error -> call routine with that file name for prod db
	#return stats based on error/success
	app.logger.debug(attachment.filename)
	attachment_name='attachment_'+attachment.filename+str(datetime.now().time())
	attachment.save(os.path.join('data',attachment_name))
	ret=content_entry(os.path.join('data',attachment_name),'localtutor')
	response={}

	print ret
	if ret>=0:
		ret=content_entry(os.path.join('data',attachment_name),'local_tutor')
		if ret>=0:
			response['result']='success'
			response['message']='Data uploaded into the database - '+str(ret)+' rows uploaded'
			
		else:
			print "problem with data entry in production database"
			response['result']='failed'
			response['message']='Data could not be uploaded - database might be in an inconsistent state'
	else:
		response['result']='failed'
		response['message']='No data uploaded'

	print response
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@app.route('/subjects')
def subjects():
	def sorter(item):
		category, subjects = item
		return len(subjects)
	client=MongoClient()
	db=client.local_tutor
	subjects=db.subjects.find()
	output=[]
	for subject in subjects:
		if 'display_name' not in subject:
			output.append(subject['name'].title())
		else:
			output.append(subject['display_name'])
	output.sort()
	category_wise={}
	subjects=db.subjects.find()
	for subject in subjects:
		if len(subject['category'])>1:
			if subject['category'] not in category_wise:
				category_wise[subject['category']]=[]
			if 'display_name' not in subject:
				category_wise[subject['category']].append(subject['name'].title())
			else:
				category_wise[subject['category']].append(subject['display_name'])
	print category_wise.items()
	sorted_category_wise=sorted(category_wise.items(),key=sorter)

	return render_template('subjects.html',output=output,category_wise=sorted_category_wise,active='subjects',app_id=app_id)

@app.route('/delete_subject',methods=['POST'])
def delete_subject():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip().lower()
		
	client=MongoClient()
	db=client.local_tutor
	print data['id']
	try:
		db.subjects.remove({'_id':ObjectId(data['id'])},True)
		response={'result':'success'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	except Exception as e:
		logger.debug(e)
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp


@app.route('/save_category',methods=['POST'])
def save_category():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip().lower()
	
	client=MongoClient()
	db=client.local_tutor
	if 'id' not in data or 'subject' not in data or 'category' not in data:
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp		
	_id=data['id']
	subject=db.subjects.find({'_id':ObjectId(_id)})
	
	try:

		subject=subject.next()
		subject['category']=data['category']
		db.subjects.save(subject)
		if data['subject'] == subject['name']:

			
			response={'result':'success_category'}
			js=json.dumps(response)
			resp=Response(js,status=200,mimetype='application/json')
			return resp
		teachers=db.teachers.find({'subject':{'$in':[subject['name']]}})
		
		results=[]
		
		try:
			for teacher in teachers:
				results.append(teacher)
		except StopIteration:
			response={'result':'success_category'}
			js=json.dumps(response)
			resp=Response(js,status=200,mimetype='application/json')
			return resp
		for teacher in results:
			
			teacher['subject'].remove(subject['name'])
			if data['subject'] not in teacher['subject']:
				teacher['subject'].append(data['subject'])

			db.teachers.save(teacher)
		prev_subject=db.subjects.find({'name':data['subject']}).count()
		
		if prev_subject>0:
			
			db.subjects.remove(subject)
		else:
			subject['name']=data['subject']
			db.subjects.save(subject)

		response={'result':'success_subject_category'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	except StopIteration:
		app.logger.error('problem saving subject category for '+data['subject'])
		response={'result':'failed_category'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp		

@app.route('/save_display_name',methods=['POST'])
def save_display_name():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	
	client=MongoClient()
	db=client.local_tutor
	if 'id' not in data or 'subject' not in data or 'display_name' not in data:
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp		
	_id=data['id']

	subject=db.subjects.find({'_id':ObjectId(_id)})
	try:
		subject=subject.next()
		if data['display_name'] == '' or len(data['display_name'])<2:
			response={'result':'failed'}
			js=json.dumps(response)
			resp=Response(js,status=200,mimetype='application/json')
			return resp	
		else:
			subject['display_name']=data['display_name']
			db.subjects.save(subject)
			response={'result':'success'}
			js=json.dumps(response)
			resp=Response(js,status=200,mimetype='application/json')
			return resp
	except StopIteration:
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	
@app.route('/subject_display')
def subject_display():

	def sorter(subject):
		return subject['name']
	client=MongoClient()
	db=client.local_tutor
	subjects=db.subjects.find()
	output=[]
	for subject in subjects:
		output.append(subject)
	output.sort(key=sorter)
	return render_template('subject_display.html',subjects=output)


@app.route('/subject_category')
def subject_category():

	def sorter(subject):
		return subject['name']
	client=MongoClient()
	db=client.local_tutor
	subjects=db.subjects.find()
	output=[]
	for subject in subjects:
		output.append(subject)
	output.sort(key=sorter)
	return render_template('subject_category.html',subjects=output)



@app.route('/create_subjects')
def create_subjects():
	password=request.args.get('password')

	if password!='createsubjectstutorack':
		return render_template('error.html')

	client=MongoClient()
	db=client.local_tutor
	teachers=db.teachers.find()
	output=[]
	output_unique=[]
	try:
		for teacher in teachers:
			match=[subject for subject in teacher['subject']]
			for individual_match in match:
				if individual_match not in output_unique:
					output.append(individual_match)
					output_unique.append(individual_match)
	except StopIteration:
		pass
	output.sort()
	for subject in output:
		prior_subject_count=db.subjects.find({'name':subject}).count()
		if prior_subject_count<=0:
			db.subjects.save({'name':subject,'category':''})
	return render_template('success_subject.html')

@app.route('/about')
def about():
	
	return render_template('about.html',app_id=app_id,active='about')

@app.route('/disclaimer')
def disclaimer():
	
	return render_template('disclaimer.html',app_id=app_id)

@app.route('/like_student_tutor',methods=['POST'])
def like_student_tutor():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'tutor_id' not in data or 'student_id' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	tutor_id=data['tutor_id']
	student_id=data['student_id']
	like=db.student_tutor_like.find({'tutor_id':tutor_id,'student_id':student_id}).count()
	if like>0:
		app.logger.error('Extra entries for student tutor association '+tutor_id+' '+student_id)
		response={}
		response={'result':'success'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp	

	like={}
	like['tutor_id']=tutor_id
	like['student_id']=student_id
	db.student_tutor_like.save(like)
	response={}
	response={'result':'success'}
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@app.route('/dislike_student_tutor',methods=['POST'])
def dislike_student_tutor():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'tutor_id' not in data or 'student_id' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	tutor_id=data['tutor_id']
	student_id=data['student_id']

	like=db.student_tutor_like.find({'tutor_id':tutor_id,'student_id':student_id}).count()
	if like==0:
		app.logger.error('No entries for student tutor association '+tutor_id+' '+student_id)
		response={}
		response={'result':'success'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	num=db.student_tutor_like.remove({'tutor_id':tutor_id,'student_id':student_id})
	app.logger.debug(str(num)+' student teacher associations removed')
	response={}
	response={'result':'success'}
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp


@app.route('/associate_student_tutor',methods=['POST'])
def associate_student_tutor():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'tutor_id' not in data or 'student_id' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	tutor_id=data['tutor_id']
	student_id=data['student_id']
	association=db.student_tutor.find({'tutor_id':tutor_id,'student_id':student_id}).count()
	if association>0:
		app.logger.error('Extra entries for student tutor association '+tutor_id+' '+student_id)
		response={}
		response={'result':'success'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	association={}
	association['tutor_id']=tutor_id
	association['student_id']=student_id
	db.student_tutor.save(association)
	response={}
	response={'result':'success'}
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@app.route('/disassociate_student_tutor',methods=['POST'])
def disassociate_student_tutor():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'tutor_id' not in data or 'student_id' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	tutor_id=data['tutor_id']
	student_id=data['student_id']

	association=db.student_tutor.find({'tutor_id':tutor_id,'student_id':student_id}).count()
	if association==0:
		app.logger.error('No entries for student tutor association '+tutor_id+' '+student_id)
		response={}
		response={'result':'success'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	num=db.student_tutor.remove({'tutor_id':tutor_id,'student_id':student_id})
	app.logger.debug(str(num)+' student teacher associations removed')
	response={}
	response={'result':'success'}
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@app.route('/friend_tutor',methods=['POST'])
def friend_tutor():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=[element.strip() for element in value]
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'friends[]' not in data or 'tutors[]' not in data:
		response={}
		response={'result':'success'}
		response['friend_tutor']=[]
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	friends=data['friends[]']
	tutors=data['tutors[]']
	result=[]
	for tutor in tutors:
		for friend in friends:
			count=db.student_tutor.find({'tutor_id':tutor,'student_id':friend}).count()
			if count>0:
				result.append(tutor)
				break
	print result
	response={}
	response={'result':'success'}
	response['friend_tutor']=result
	js=json.dumps(response)
	print response
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@app.route('/friend_tutor_name',methods=['POST'])
def friend_tutor_name():
	data={}
	counter=0
	for name,value in dict(request.form).iteritems():
		if name=='tutor':
			data[name]=value[0].strip()
		else:
			data[name]=[element.strip() for element in value]
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'friends[]' not in data or 'tutor' not in data:
		response={}
		response={'result':'success'}
		response['friend_tutor']=[]
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	friends=data['friends[]']
	tutor=data['tutor']
	result=[]
	for friend in friends:
		count=db.student_tutor.find({'tutor_id':tutor,'student_id':friend}).count()
		if count>0:
			result.append(friend)
			
	print result
	response={}
	response={'result':'success'}
	response['friend_tutor']=result
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp


@app.route('/tutor')
def tutor():
	tutor_id=request.args.get('id')
	client=MongoClient()
	db=client.local_tutor
	if tutor_id is None:
		return render_template('error.html')
	tutor=db.teachers.find({'_id':ObjectId(tutor_id)})
	display_subjects=[]
	try:
		tutor=tutor.next()
		for subject in tutor['subject']:
			actual_subject=db.subjects.find({'name':subject})
			try:
				actual_subject=actual_subject.next()
				if 'display_name' not in actual_subject:
					display_subjects.append(actual_subject['name'].title())
				else:
					display_subjects.append(actual_subject['display_name'])
			except StopIteration:
				pass
		if tutor['area'] != 'online':
			return render_template('tutor.html',tutor=tutor,display_subjects=display_subjects,app_id=app_id)
		else:
			return render_template('tutor_online.html',tutor=tutor,display_subjects=display_subjects,app_id=app_id)
	except StopIteration:
		return render_template('error.html')

@app.route('/tutor_edit')
def tutor_edit():
	tutor_id=request.args.get('id')
	client=MongoClient()
	db=client.local_tutor
	if tutor_id is None:
		return render_template('error.html')
	tutor=db.teachers.find({'_id':ObjectId(tutor_id)})
	display_subjects=[]
	try:
		tutor=tutor.next()
				
		return render_template('tutor_edit.html',tutor=tutor)
	except StopIteration:
		return render_template('error.html')

@app.route('/tutor_delete')
def tutor_delete():
	tutor_id=request.args.get('id')
	if not tutor_id or len(tutor_id.strip())<1:
		return redirect('/')
	client=MongoClient()
	db=client.local_tutor
	teacher=db.teachers.find({'_id':ObjectId(tutor_id)})
	try:
		teacher=teacher.next()
		db.teachers.remove({'_id':ObjectId(tutor_id)})
		app.logger.debug('Deleted tutor id:'+tutor_id)
		return redirect('/')
	except StopIteration:
		return redirect('/')


@app.route('/tutor_edit_save',methods=['POST'])
def tutor_edit_save():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip().lower()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if '_id' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp		
	tutor=db.teachers.find({'_id':ObjectId(data['_id'])})
	try:
		tutor=tutor.next()
		if data['name']!='' or len(data['name'])>1:
			tutor['name']=data['name']
			tutor['subject']=[subject.strip().lower() for subject in data['subject'].split(',')]
			tutor['contact_number']=[contact_number.strip().lower() for contact_number in data['contact_number'].split(',')]
			tutor['geographical_location']=data['geographical_location']
			tutor['area']=data['area']
			tutor['email']=data['email']
			tutor['age_group']=data['age_group']
			tutor['venue']=data['venue']
			tutor['classroom_type']=data['classroom_type']
			tutor['teacher_type']=data['teacher_type']

			for subject in tutor['subject']:
				actual_subject=db.subjects.find({'name':subject})
				try:
					actual_subject=actual_subject.next()
				except StopIteration:
					actual_subject={}
					actual_subject['name']=subject
					actual_subject['category']=''
					db.subjects.save(actual_subject)

			db.teachers.save(tutor)

		else:
			response={}
			response={'result':'failed'}
			js=json.dumps(response)
			resp=Response(js,status=200,mimetype='application/json')
			return resp			

	except StopIteration:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp		

	response={}
	response={'result':'success'}
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@login_required
@app.route('/tutor_profile_edit_save',methods=['POST'])
def tutor_profile_edit_save():
	data={}
	for name,value in dict(request.form).iteritems():
		if name=='usp' or name=='announcement':
			data[name]=value[0]
		else:
			data[name]=value[0].strip().lower()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if '_id' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp	

	if data['user_id']!=current_user.id:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp					

	tutor=db.teachers.find({'_id':ObjectId(data['_id'])})
	try:
		tutor=tutor.next()
		if data['name']!='' or len(data['name'])>1:
			tutor['name']=data['name']
			tutor['subject']=[subject.strip().lower() for subject in data['subject'].split(',')]
			tutor['contact_number']=[contact_number.strip().lower() for contact_number in data['contact_number'].split(',')]
			tutor['geographical_location']=data['geographical_location']
			tutor['area']=data['area']
			tutor['email']=data['email']
			tutor['age_group']=data['age_group']
			tutor['venue']=data['venue']
			tutor['classroom_type']=data['classroom_type']
			tutor['teacher_type']=data['teacher_type']
			tutor['usp']=data['usp']
			
			ist=timezone('Asia/Kolkata')
			ist_now=datetime.now(ist)
			date=ist_now.strftime('%d/%m/%Y')
			tutor['announcement']=data['announcement']
			tutor['date_announcement']=date

			for subject in tutor['subject']:
				actual_subject=db.subjects.find({'name':subject})
				try:
					actual_subject=actual_subject.next()
				except StopIteration:
					actual_subject={}
					actual_subject['name']=subject
					actual_subject['category']=''
					db.subjects.save(actual_subject)

			db.teachers.save(tutor)

		else:
			response={}
			response={'result':'failed'}
			js=json.dumps(response)
			resp=Response(js,status=200,mimetype='application/json')
			return resp			

	except StopIteration:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp		

	response={}
	response={'result':'success'}
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

def tagger(text):
	tagger=pycrfsuite.Tagger()
	tagger.open('static/classifier/crf_classifier_main.crfsuite')
	
	tokenized_text=nltk.word_tokenize(text)
	history='O'
	feature_set=[]
	for i,word in enumerate(tokenized_text):
		features=npchunk_features(tokenized_text,i,history)
		feature_set.append(features)
	result=zip(tokenized_text,tagger.tag(feature_set))
	
	tagged_instance=[(w,'NN',c) for (w,c) in result]
	tree=nltk.chunk.conlltags2tree(tagged_instance)
	tagged_subjects=[]
	tagged_areas=[]
	for subtree in tree.subtrees(filter=lambda t: t.label() == 'SUBJECT'):
		print 'SUBJECTS'
		print subtree.leaves()
		subject_parts=[sub for (sub,tag) in subtree.leaves()]
		tagged_subjects.append(' '.join(subject_parts))
		
		
	for subtree in tree.subtrees(filter=lambda t: t.label() == 'LOCATION'):
		print 'AREAS'
		print subtree.leaves()
		area_parts=[area for (area,tag) in subtree.leaves()]
		tagged_areas.append(' '.join(area_parts))
		
	print (tagged_subjects,tagged_areas)
	return(tagged_subjects,tagged_areas)

def prepare_query_machine_filtered(query,size,start_from,filter_areas, filter_subjects,filter_venues,is_filter,
									actual_tagged_subjects,actual_tagged_areas):

	print 'prepare_machine_filtered query function'
	payload={}
	payload['query']={}
	payload['query']['filtered']={}
	payload['query']['filtered']['query']={}
	payload['query']['filtered']['query']['bool']={}
	payload['query']['filtered']['query']['bool']['should']=[]

	payload['query']['filtered']['query']['bool']['must']=[]

	payload_machine={}
	payload_machine['query']={}
	payload_machine['query']['bool']={}
	payload_machine['query']['bool']['should']=[]
	for sub in actual_tagged_subjects:
		#payload_machine['query']['bool']['should'].append(
		#	{'constant_score':{'query':{'match':{'subject' : {'query':sub, 'type': 'phrase'}}}}})
		payload_machine['query']['bool']['should'].append(
			{'term' : {'subject.not_analyzed':sub}})

	payload['query']['filtered']['query']['bool']['must'].append(payload_machine)

	payload_machine={}
	payload_machine['query']={}
	payload_machine['query']['bool']={}
	payload_machine['query']['bool']['should']=[]
	for sub in actual_tagged_areas:
		payload_machine['query']['bool']['should'].append(
			{'constant_score':{'query':{'match':{'area' : {'query':sub, 'type': 'phrase'}}}}})

	payload['query']['filtered']['query']['bool']['must'].append(payload_machine)




	constant_score_query={}
	constant_score_query['constant_score']={}
	constant_score_query['constant_score']['query']={}
	constant_score_query['constant_score']['query']['match']={}
	constant_score_query['constant_score']['query']['match']['subject']={}
	constant_score_query['constant_score']['query']['match']['subject']['query']=query
	constant_score_query['constant_score']['query']['match']['subject']['fuzziness']=1

	constant_score_query4={}
	constant_score_query4['constant_score']={}
	constant_score_query4['constant_score']['query']={}
	constant_score_query4['constant_score']['query']['match']={}
	constant_score_query4['constant_score']['query']['match']['subject']={}
	constant_score_query4['constant_score']['query']['match']['subject']['query']=query
	

	#payload['query']['filtered']['query']['bool']['should'].append(constant_score_query)
	payload['query']['filtered']['query']['bool']['should'].append(constant_score_query4)

	constant_score_query1={}
	constant_score_query1['constant_score']={}
	constant_score_query1['constant_score']['query']={}
	constant_score_query1['constant_score']['query']['match']={}
	constant_score_query1['constant_score']['query']['match']['area']={}
	constant_score_query1['constant_score']['query']['match']['area']['query']=query
	#constant_score_query1['constant_score']['query']['match']['area']['fuzziness']=1

	constant_score_query6={}
	constant_score_query6['constant_score']={}
	constant_score_query6['constant_score']['query']={}
	constant_score_query6['constant_score']['query']['match']={}
	constant_score_query6['constant_score']['query']['match']['subject']={}
	constant_score_query6['constant_score']['query']['match']['subject']['query']=query
	
	constant_score_query6['constant_score']['query']['match']['subject']['type']='phrase'



	constant_score_query2={}
	constant_score_query2['constant_score']={}
	constant_score_query2['constant_score']['query']={}
	constant_score_query2['constant_score']['query']['match']={}
	constant_score_query2['constant_score']['query']['match']['name']={}
	constant_score_query2['constant_score']['query']['match']['name']['query']=query
	constant_score_query2['constant_score']['query']['match']['name']['type']='phrase'
	constant_score_query2['constant_score']['query']['match']['name']['fuzziness']=1	




	constant_score_query3={}
	constant_score_query3['constant_score']={}
	constant_score_query3['constant_score']['query']={}
	constant_score_query3['constant_score']['query']['match']={}
	constant_score_query3['constant_score']['query']['match']['geographical_location']={}
	constant_score_query3['constant_score']['query']['match']['geographical_location']['query']=query
	constant_score_query3['constant_score']['query']['match']['geographical_location']['fuzziness']=1		

	constant_score_query5={}
	constant_score_query5['constant_score']={}
	constant_score_query5['constant_score']['query']={}
	constant_score_query5['constant_score']['query']['match']={}
	constant_score_query5['constant_score']['query']['match']['subject.not_analyzed']={}
	constant_score_query5['constant_score']['query']['match']['subject.not_analyzed']['query']=query
	

	bool_query={}
	bool_query['bool']={}
	bool_query['bool']['should']=[]
	bool_query['bool']['should'].append(constant_score_query1)

	bool_query2={}
	bool_query2['bool']={}
	bool_query2['bool']['should']=[]
	bool_query2['bool']['should'].append(constant_score_query2)
	#bool_query2['bool']['should'].append(constant_score_query3)
	bool_query2['bool']['should'].append(constant_score_query5)
	bool_query2['bool']['should'].append(constant_score_query6)

	bool_query['bool']['should'].append(bool_query2)
	

	payload['query']['filtered']['query']['bool']['should'].append(bool_query)	

	if is_filter:
		bool_query={}
		bool_query['bool']={}
		bool_query['bool']['should']=[]
		for subject in filter_subjects:
			bool_query['bool']['should'].append({'term': {'subject.not_analyzed':subject}})
		for area in filter_areas:
			bool_query['bool']['should'].append({'term': {'area.not_analyzed':area}})
		for venue in filter_venues:
			bool_query['bool']['should'].append({'term': {'venue':venue}})
		payload['query']['filtered']['filter']=bool_query

	

	print payload

	print 'http://localhost:9200/local_tutor/teachers/_search?size='+str(size)+'&from='+str(start_from)
	r=requests.post('http://localhost:9200/local_tutor/teachers/_search?size='+str(size)+'&from='+str(start_from),json=payload)
	
	json_response=json.loads(r.text)
	return json_response

def prepare_query_filtered(query,size,start_from,filter_areas, filter_subjects,filter_venues,is_filter):
	
	'prepare_filter query function'
	payload={}
	payload['query']={}
	payload['query']['filtered']={}
	payload['query']['filtered']['filter']={}
	

	if is_filter:
		bool_query={}
		bool_query['bool']={}
		bool_query['bool']['should']=[]
		#for subject in filter_subjects:

		#	bool_query['bool']['should'].append({'term': {'subject.not_analyzed':subject}})
		for area in filter_areas:
			bool_query['bool']['should'].append({'term': {'area.not_analyzed':area}})
		for venue in filter_venues:
			bool_query['bool']['should'].append({'term': {'venue':venue}})
		
		bool_query['bool']['must']=[]
		bool_query_inner={}
		bool_query_inner['bool']={}
		bool_query_inner['bool']['must']=[]
		for subject in filter_subjects:
			bool_query['bool']['must'].append({'term': {'subject.not_analyzed':subject}})
		
		
		payload['query']['filtered']['filter']=bool_query
	else:
		bool_query={}
		bool_query['bool']={}
		bool_query['bool']['should']=[]
		bool_query['bool']['should'].append({'term':{'subject.not_analyzed':query}})
		payload['query']['filtered']['filter']=bool_query

	print payload

	print 'http://localhost:9200/local_tutor/teachers/_search?size='+str(size)+'&from='+str(start_from)
	r=requests.post('http://localhost:9200/local_tutor/teachers/_search?size='+str(size)+'&from='+str(start_from),json=payload)
	
	json_response=json.loads(r.text)
	return json_response


def prepare_query(query,size,start_from,filter_areas, filter_subjects,filter_venues,is_filter):

	print 'prepare query function'
	payload={}
	payload['query']={}
	payload['query']['filtered']={}
	payload['query']['filtered']['query']={}
	payload['query']['filtered']['query']['bool']={}
	payload['query']['filtered']['query']['bool']['should']=[]

	constant_score_query={}
	constant_score_query['constant_score']={}
	constant_score_query['constant_score']['query']={}
	constant_score_query['constant_score']['query']['match']={}
	constant_score_query['constant_score']['query']['match']['subject']={}
	constant_score_query['constant_score']['query']['match']['subject']['query']=query
	constant_score_query['constant_score']['query']['match']['subject']['fuzziness']=1

	constant_score_query4={}
	constant_score_query4['constant_score']={}
	constant_score_query4['constant_score']['query']={}
	constant_score_query4['constant_score']['query']['match']={}
	constant_score_query4['constant_score']['query']['match']['subject']={}
	constant_score_query4['constant_score']['query']['match']['subject']['query']=query
	

	#payload['query']['filtered']['query']['bool']['should'].append(constant_score_query)
	payload['query']['filtered']['query']['bool']['should'].append(constant_score_query4)

	constant_score_query1={}
	constant_score_query1['constant_score']={}
	constant_score_query1['constant_score']['query']={}
	constant_score_query1['constant_score']['query']['match']={}
	constant_score_query1['constant_score']['query']['match']['area']={}
	constant_score_query1['constant_score']['query']['match']['area']['query']=query
	#constant_score_query1['constant_score']['query']['match']['area']['fuzziness']=1

	constant_score_query6={}
	constant_score_query6['constant_score']={}
	constant_score_query6['constant_score']['query']={}
	constant_score_query6['constant_score']['query']['match']={}
	constant_score_query6['constant_score']['query']['match']['subject']={}
	constant_score_query6['constant_score']['query']['match']['subject']['query']=query
	
	constant_score_query6['constant_score']['query']['match']['subject']['type']='phrase'



	constant_score_query2={}
	constant_score_query2['constant_score']={}
	constant_score_query2['constant_score']['query']={}
	constant_score_query2['constant_score']['query']['match']={}
	constant_score_query2['constant_score']['query']['match']['name']={}
	constant_score_query2['constant_score']['query']['match']['name']['query']=query
	constant_score_query2['constant_score']['query']['match']['name']['type']='phrase'
	#constant_score_query2['constant_score']['query']['match']['name']['fuzziness']=1	




	constant_score_query3={}
	constant_score_query3['constant_score']={}
	constant_score_query3['constant_score']['query']={}
	constant_score_query3['constant_score']['query']['match']={}
	constant_score_query3['constant_score']['query']['match']['geographical_location']={}
	constant_score_query3['constant_score']['query']['match']['geographical_location']['query']=query
	constant_score_query3['constant_score']['query']['match']['geographical_location']['fuzziness']=1		

	constant_score_query5={}
	constant_score_query5['constant_score']={}
	constant_score_query5['constant_score']['query']={}
	constant_score_query5['constant_score']['query']['match']={}
	constant_score_query5['constant_score']['query']['match']['subject.not_analyzed']={}
	constant_score_query5['constant_score']['query']['match']['subject.not_analyzed']['query']=query
	

	bool_query={}
	bool_query['bool']={}
	bool_query['bool']['should']=[]
	bool_query['bool']['should'].append(constant_score_query1)

	bool_query2={}
	bool_query2['bool']={}
	bool_query2['bool']['should']=[]
	bool_query2['bool']['should'].append(constant_score_query2)
	#bool_query2['bool']['should'].append(constant_score_query3)
	bool_query2['bool']['should'].append(constant_score_query5)
	bool_query2['bool']['should'].append(constant_score_query6)

	bool_query['bool']['should'].append(bool_query2)
	

	payload['query']['filtered']['query']['bool']['should'].append(bool_query)	

	if is_filter:
		bool_query={}
		bool_query['bool']={}
		bool_query['bool']['should']=[]
		for subject in filter_subjects:
			bool_query['bool']['should'].append({'term': {'subject.not_analyzed':subject}})
		for area in filter_areas:
			bool_query['bool']['should'].append({'term': {'area.not_analyzed':area}})
		for venue in filter_venues:
			bool_query['bool']['should'].append({'term': {'venue':venue}})
		payload['query']['filtered']['filter']=bool_query

	

	print payload

	print 'http://localhost:9200/local_tutor/teachers/_search?size='+str(size)+'&from='+str(start_from)
	r=requests.post('http://localhost:9200/local_tutor/teachers/_search?size='+str(size)+'&from='+str(start_from),json=payload)
	
	json_response=json.loads(r.text)
	return json_response



@app.route('/search',methods=['GET','POST'])
def search():
	if request.method=='POST':
		query=request.args.get('subject')
		
		page=request.args.get('page')
		
		try:
			page=int(page)
		except Exception,ValueError:
			page=1
		if not page or page<1 or page>10:
			page=1

		if not query or query.strip()=='':
			return render_template('search_error.html')

		query=query.lower()
		data={}
		for name,value in dict(request.form).iteritems():
			data[name]=[element.strip() for element in value]
		app.logger.debug(str(data))

		client=MongoClient()
		db=client.local_tutor

		filter_subjects_string=data['subject_selected'][0].split('|')
		
		filter_areas_string=data['areas_selected'][0].split('|')

		filter_venue_string=data['venue_selected'][0].split('|')


		
		areas_checkboxes=data['areas_checkboxes'][0].split('|')
		subject_checkboxes=data['subject_checkboxes'][0].split('|')
		venue_checkboxes=data['venue_checkboxes'][0].split('|')

		actual_tagged_subjects=[s for s in data['actual_tagged_subjects'][0].split('|') if len(s)>0]
		actual_tagged_areas=[s for s in data['actual_tagged_areas'][0].split('|') if len(s)>0]


		print actual_tagged_subjects
		print actual_tagged_areas

		filter_subjects=[]
		filter_areas=[]
		filter_venues=[]
		is_filter=True
		is_machine_filtered=False
		


		if len(actual_tagged_subjects)>0 or len(actual_tagged_areas)>0:
			is_machine_filtered=True

		for subjects in filter_subjects_string:
			if len(subjects)>0:
				
				filter_subjects.append(subjects)
		for areas in filter_areas_string:
			if len(areas)>0:
				
				filter_areas.append(areas)
		for venue in filter_venue_string:
			if venue.lower()=='center':
				filter_venues.append('center')
				filter_venues.append('centre')
			if venue.lower()=='student\'s home':
				filter_venues.append('students home')


		print filter_areas
		print filter_subjects
		print filter_venues

		is_pre_filter=request.args.get('is_pre_filter')

		if is_pre_filter and is_pre_filter=='y':
			categories=get_category([query])
			if len(categories)<1:
				response=prepare_query_filtered(query,10,(page-1)*10,filter_areas,[query],filter_venues,is_filter)
			else:
				response=prepare_query_machine_filtered(query,10,(page-1)*10,filter_areas,filter_subjects,
													filter_venues,is_filter,actual_tagged_subjects,actual_tagged_areas)
				
		else:
			if is_machine_filtered:
				response=prepare_query_machine_filtered(query,10,(page-1)*10,filter_areas,filter_subjects,
													filter_venues,is_filter,actual_tagged_subjects,actual_tagged_areas)
			else:
				response=prepare_query(query,10,(page-1)*10,filter_areas,filter_subjects,filter_venues,is_filter)
		
		


		total=response['hits']['total']
		max_score=response['hits']['max_score']
		results=response['hits']['hits']
		areas=[]
		subjects=[]
		paginated_results=[]
		for teacher in results:
			actual_data=teacher['_source']
			actual_data['_id']=teacher['_id']
			paginated_results.append(actual_data)
			

		areas=[]
		subjects=[]
		venues=[]
		for area in areas_checkboxes:
			if len(area)<1:
				continue
			if area in filter_areas:
				areas.append((area,True))
			else:
				areas.append((area,False))
		for subject in subject_checkboxes:
			if len(subject)<1:
				continue
			if subject in filter_subjects:
				subjects.append((subject,True))
			else:
				subjects.append((subject,False))

		for venue in venue_checkboxes:
			if len(venue)<1:
				continue

			if venue=='Student\'s Home':

				if 'students home' in filter_venues:
					venues.append((venue,True))
				else:
					venues.append((venue,False))
			if venue=='Center':
				if 'center' in filter_venues or 'centre' in filter_venues:
					venues.append((venue,True))
				else:
					venues.append((venue,False))




		filter_results=False
		if len(areas)>1 or len(subjects)>1 or len(venues)>1:
			filter_results=True


		student_tutor_assoc={}
		if hasattr(current_user,'id'):
			for teacher in paginated_results:
				student_teacher=db.student_tutor.find({'tutor_id':str(teacher['_id']),'student_id':current_user.fb_id}).count()
				if student_teacher>0:
					student_tutor_assoc[teacher['_id']]=True
		print student_tutor_assoc
		total_pages=math.ceil(total/10.0)
		if total_pages>10:
			total_pages=10

		teacher_likes={}

		for teacher in paginated_results:
			
			teacher['likes']=db.student_tutor_like.find({'tutor_id':str(teacher['_id'])}).count()
			
		student_tutor_like={}
		if hasattr(current_user,'id'):
			for teacher in paginated_results:
				student_teacher=db.student_tutor_like.find({'tutor_id':str(teacher['_id']),'student_id':current_user.id}).count()
				if student_teacher>0:
					student_tutor_like[teacher['_id']]=True
		title='- Search results for '+query
		return render_template('search_result.html',results=paginated_results,query=query,length=(len(paginated_results)+1)/2,
								student_tutor_assoc=student_tutor_assoc,total_pages=total_pages,page=page,filter_results=filter_results,
								areas=areas,subjects=subjects,venue=venues,classify='n',app_id=app_id,total=total,
								actual_tagged_subjects='|'.join(actual_tagged_subjects),
								actual_tagged_areas='|'.join(actual_tagged_areas),student_tutor_like=student_tutor_like,title=title)

	try:
		query=request.args.get('subject')
		is_classify=request.args.get('classify')
		page=request.args.get('page')
		print page
		
		try:
			page=int(page)
		except Exception,ValueError:
			page=1
		if not page or page<1 or page>10:
			page=1
		if not query or query.strip()=='':
			return render_template('search_error.html')

		query=query.lower().strip()
		print page
		client=MongoClient()
		db=client.local_tutor

		

		is_pre_filter=request.args.get('is_pre_filter')

		is_machine_filtered=False
		actual_tagged_subjects=[]
		actual_tagged_areas=[]
		categories=[]
		filter_subjects=[]

		if is_pre_filter and is_pre_filter=='y':
			categories=get_category([query])
			if len(categories)<1:
				response=prepare_query_filtered(query,500,0,None,None,None,False)
			else:
				for tagged_category in categories:
					print 'category:'+tagged_category
					subjects_in_categories=db.subjects.find({'category':tagged_category})
					for s in subjects_in_categories:
						filter_subjects.append(s['name'])
					filter_subjects.append(tagged_category)
				
				response=prepare_query_machine_filtered(query,500,0,None,None,None,False,filter_subjects,actual_tagged_areas)
				
			is_pre_filter='y'
		else:
			print 'check 0'
			tagged_subjects, tagged_areas = tagger(query)
			print 'tagged_subjects:'+str(tagged_subjects)
			print 'tagged_areas:'+str(tagged_areas)
			print len(tagged_subjects)

			for a in tagged_areas:
				if db.teachers.find({'area':a}).count()>0:
					actual_tagged_areas.append(a)

			tagged_categories=get_category(tagged_subjects)


			if len(tagged_categories)>0:


				for tagged_category in tagged_categories:
					print 'category:'+tagged_category
					subjects_in_categories=db.subjects.find({'category':tagged_category})
					for s in subjects_in_categories:
						actual_tagged_subjects.append(s['name'])

			for sub in tagged_subjects:
				print sub
				if db.subjects.find({'name':sub}).count()>0:
					actual_tagged_subjects.append(sub)
			

			print 'actual subjects:'+str(actual_tagged_subjects)
			print 'actual areas:'+str(actual_tagged_areas)

			if len(actual_tagged_subjects)>0 or len(actual_tagged_areas)>0:
				is_machine_filtered=True

			if is_machine_filtered==True:
				print 'machine_filtered results'
				print actual_tagged_subjects
				print actual_tagged_areas
				response=prepare_query_machine_filtered(query,500,0,None,None,None,False,actual_tagged_subjects,actual_tagged_areas)
			else:
				response=prepare_query(query,500,0,None,None,None,False)
			is_pre_filter='n'

		print 'check 2'
		total=response['hits']['total']
		max_score=response['hits']['max_score']
		results=response['hits']['hits']
		areas=[]
		subjects=[]
		areas_duplicate=[]
		subjects_duplicate=[]
		paginated_results=[]
		sh_present=False
		center_present=False
		for teacher in results:
			actual_data=teacher['_source']
			actual_data['_id']=teacher['_id']
			paginated_results.append(actual_data)
			if actual_data['area'] not in areas_duplicate:
				areas_duplicate.append(actual_data['area'])
				areas.append((actual_data['area'],False))
			for subject in actual_data['subject']:
				if subject not in subjects_duplicate and len(subject)>0:
					subjects_duplicate.append(subject)
					subjects.append((subject,False))
			if actual_data['venue']=='center' or actual_data['venue']=='centre':
				center_present=True
			if actual_data['venue']=='students home':
				sh_present=True
		venue=[]
		if sh_present==True:
			venue.append(('Student\'s Home',False))
		if center_present==True:
			venue.append(('Center',False))


		areas.sort()
		if ('online',False) in areas:
			areas.remove(('online',False))
			areas=[('online',False)]+areas

		app.logger.debug(areas)

		subjects.sort()


		if is_pre_filter=='y' and len(categories)<1:
			subjects=[]
		new_subjects=[]
		if is_machine_filtered and len(actual_tagged_subjects)>=1:
			for s in subjects:
				for a in actual_tagged_subjects:
					if s[0].find(a)!=-1:
						new_subjects.append((s[0],False))
						break
			subjects=new_subjects
		if is_pre_filter and len(categories)>0:
			for s in subjects:
				for a in filter_subjects:
					if s[0].find(a)!=-1:
						new_subjects.append((s[0],False))
						break
			subjects=new_subjects

		if len(subjects)==1:
			subjects=[]
		if is_machine_filtered and len(actual_tagged_areas)==1:
			areas=[]

		filter_results=False
		if len(areas)>1 or len(subjects)>1 or len(venue)>1:
			filter_results=True


		tagged_subjects=[]
		tagged_areas=[]

		if is_pre_filter and is_pre_filter=='y':

			if len(categories)<1:
				response=prepare_query_filtered(query,10,(page-1)*10,None,None,None,False)
			else:
				response=prepare_query_machine_filtered(query,10,(page-1)*10,None,None,None,False,
														filter_subjects,actual_tagged_areas)
				
			is_pre_filter='y'
			actual_tagged_subjects=filter_subjects
		else:


			if is_machine_filtered==True:
				response=prepare_query_machine_filtered(query,10,(page-1)*10,None,None,None,False,
														actual_tagged_subjects,actual_tagged_areas)
			else:
				response=prepare_query(query,10,(page-1)*10,None,None,None,False)
			is_pre_filter='n'
		

		total=response['hits']['total']
		max_score=response['hits']['max_score']
		results=response['hits']['hits']
		
		paginated_results=[]
		for teacher in results:
			actual_data=teacher['_source']
			actual_data['_id']=teacher['_id']
			paginated_results.append(actual_data)
			

			
		


		student_tutor_assoc={}
		if hasattr(current_user,'id'):
			for teacher in paginated_results:
				student_teacher=db.student_tutor.find({'tutor_id':str(teacher['_id']),'student_id':current_user.fb_id}).count()
				if student_teacher>0:
					student_tutor_assoc[teacher['_id']]=True

		print student_tutor_assoc
		total_pages=math.ceil(total/10.0)
		if total_pages>10:
			total_pages=10

		for teacher in paginated_results:
			
			teacher['likes']=db.student_tutor_like.find({'tutor_id':str(teacher['_id'])}).count()

		student_tutor_like={}
		if hasattr(current_user,'id'):
			for teacher in paginated_results:
				student_teacher=db.student_tutor_like.find({'tutor_id':str(teacher['_id']),'student_id':current_user.id}).count()
				if student_teacher>0:
					student_tutor_like[teacher['_id']]=True

		
		title='- Search results for '+query

		return render_template('search_result.html',results=paginated_results,query=query,length=(len(paginated_results)+1)/2,
								student_tutor_assoc=student_tutor_assoc,total_pages=total_pages,page=page,filter_results=filter_results,
								areas=areas,subjects=subjects,classify='n',app_id=app_id,total=total,venue=venue,
								actual_tagged_subjects='|'.join(actual_tagged_subjects),
								actual_tagged_areas='|'.join(actual_tagged_areas),student_tutor_like=student_tutor_like,title=title)
	except Exception as e:
		app.logger.error(str(e))



		
def get_category(tagged_subjects):
	client=MongoClient()
	db=client.local_tutor
	subjects=db.subjects.find()
	categories=[]
	for subject in subjects:
		if subject['category'] not in categories:
			categories.append(subject['category'])
	tagged_categories=[]
	for tagged_subject in tagged_subjects:
		if tagged_subject in categories:
			tagged_categories.append(tagged_subject)
	return tagged_categories





@app.route('/options')
def options():
	q=request.args.get('subject')
	q=q.strip().lower()
	client=MongoClient()
	db=client.local_tutor
	
	pattern=re.compile('.*'+q+'.*')
	
	teachers=db.teachers.find({'subject':{'$in':[pattern]}})
	
	output=[]
	output_unique=[]
	try:
		for teacher in teachers:
			match=[subject for subject in teacher['subject'] if re.search(pattern,subject)]
			for individual_match in match:
				if individual_match not in output_unique:
					output.append({'value':individual_match})
					output_unique.append(individual_match)
	except StopIteration:
		pass

	#app.logger.debug(output)
	js=json.dumps(output)
	
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@login_required
@app.route('/result_feedback')
def result_feedback():
	client=MongoClient()
	db=client.local_tutor
	feedback=db.satisfaction.find()
	return render_template('result_feedback.html',feedback=feedback)

@app.route('/result_satisfaction_comment',methods=['POST'])
def result_satisfaction_comment():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'satisfy_id' not in data or 'comment' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp	

	satisfy=db.satisfaction.find({'_id':ObjectId(data['satisfy_id'])})
	try:
		satisfy=satisfy.next()
		satisfy['comment']=data['comment']
		db.satisfaction.save(satisfy)
		response={}
		response={'result':'success'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	except:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp			



@app.route('/result_satisfaction',methods=['POST'])
def result_satisfaction():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor

	if '_id' not in data or 'satisfy' not in data or 'query' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	user=db.users.find({'_id':ObjectId(data['_id'])})
	try:
		user=user.next()
		result={}
		result['id']=str(user['_id'])
		result['name']=user['name']
		result['query']=data['query']
		result['satisfy']=data['satisfy']
		_id=db.satisfaction.save(result)
		response={}
		response={'result':'success'}
		response={'satisfy_id':str(_id)}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	except:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
		

if True:
	import logging
	from logging.handlers import RotatingFileHandler
	file_handler = RotatingFileHandler('/home/uday/localtutor/logs/application.log', maxBytes=1024 * 1024 * 100, backupCount=20)
	file_handler.setLevel(logging.DEBUG)
	formatter = logging.Formatter("%(asctime)s - %(funcName)s - %(levelname)s - %(message)s")
	file_handler.setFormatter(formatter)
	app.logger.addHandler(file_handler)
	app.logger.error(str(app.config))

if __name__ == "__main__":
	
	app.run()