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

SECRET_KEY='SECRET'


SALT='123456789passwordsalt'

app = Flask(__name__)
app.debug=True
app.secret_key=SECRET_KEY


REMEMBER_COOKIE_DURATION=timedelta(days=365)
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


	features.append('is_gazette='+is_gazette)
	features.append('w_is_gazette='+word+'_'+is_gazette)
	features.append('p_bigram_gazette='+p_bigram_gazette)
	features.append('n_bigram_gazette='+n_bigram_gazette)
	return features


class User(UserMixin):
    def __init__(self, name, _id, fb_id,active=True):
        self.name = name
        self.id = _id
        self.fb_id=fb_id
        self.active=active
    
    def is_active(self):
        return self.active
        
    
    def get_auth_token(self):
        """
        Encode a secure token for cookie
        """
        data = [str(self.id), self.fb_id]
        return login_serializer.dumps(data)

@login_manager.user_loader
def load_user(_id):

	app.logger.debug("in load_user")
	client=MongoClient()
	db=client.local_tutor
	user=db.users.find({'_id':ObjectId(_id)})
	try:
		user=user.next()
		
		ret_user=User(name=user['name'],fb_id=user['fb_id'],_id=str(user['_id']),active=True)
		return ret_user
	except StopIteration:
		return None

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
    if user and data[1] == user.fb_id:
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
	return render_template('main_page.html')

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
			return redirect(data['redirect_url'])
		else:
			return render_template('error.html')
	except StopIteration:
		user={}
		user['fb_id']=data['fb_user_id']
		user['name']=data['fb_user_name']
		_id=db.users.save(user)
		ret_user=User(name=user['name'],_id=_id,fb_id=user['fb_id'])
		app.logger.debug(ret_user)
		app.logger.debug(ret_user.active)
		if login_user(ret_user, force=True):
			return redirect(data['redirect_url'])
		else:
			return render_template('error.html')
	
@app.route('/logout')
def logout():
	logout_user()
	flash("Logged out!")
	redirect_url=request.args.get('redirect_url')
	if redirect_url is not None:
		return redirect(redirect_url)
	redirect('/')

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

	return render_template('subjects.html',output=output,category_wise=sorted_category_wise)

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
	
	return render_template('about.html')

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
			return render_template('tutor.html',tutor=tutor,display_subjects=display_subjects)
		else:
			return render_template('tutor_online.html',tutor=tutor,display_subjects=display_subjects)
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
	subject=''
	area=''
	for subtree in tree.subtrees(filter=lambda t: t.label() == 'SUBJECT'):
		print subtree.leaves()
		subject_parts=[sub for (sub,tag) in subtree.leaves()]
		subject=' '.join(subject_parts)
		
	for subtree in tree.subtrees(filter=lambda t: t.label() == 'LOCATION'):
		print subtree.leaves()
		area_parts=[area for (area,tag) in subtree.leaves()]
		area=' '.join(area_parts)

	return(subject,area)

def prepare_query(query,start_from,filter_areas, filter_subjects,is_filter):
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
	

	payload['query']['filtered']['query']['bool']['should'].append(constant_score_query)
	payload['query']['filtered']['query']['bool']['should'].append(constant_score_query4)

	constant_score_query1={}
	constant_score_query1['constant_score']={}
	constant_score_query1['constant_score']['query']={}
	constant_score_query1['constant_score']['query']['match']={}
	constant_score_query1['constant_score']['query']['match']['area']={}
	constant_score_query1['constant_score']['query']['match']['area']['query']=query
	constant_score_query1['constant_score']['query']['match']['area']['fuzziness']=1


	constant_score_query2={}
	constant_score_query2['constant_score']={}
	constant_score_query2['constant_score']['query']={}
	constant_score_query2['constant_score']['query']['match']={}
	constant_score_query2['constant_score']['query']['match']['name']={}
	constant_score_query2['constant_score']['query']['match']['name']['query']=query
	constant_score_query2['constant_score']['query']['match']['name']['fuzziness']=1	


	constant_score_query3={}
	constant_score_query3['constant_score']={}
	constant_score_query3['constant_score']['query']={}
	constant_score_query3['constant_score']['query']['match']={}
	constant_score_query3['constant_score']['query']['match']['geographical_location']={}
	constant_score_query3['constant_score']['query']['match']['geographical_location']['query']=query
	constant_score_query3['constant_score']['query']['match']['geographical_location']['fuzziness']=1		

	bool_query={}
	bool_query['bool']={}
	bool_query['bool']['should']=[]
	bool_query['bool']['should'].append(constant_score_query1)
	bool_query['bool']['should'].append(constant_score_query2)
	bool_query['bool']['should'].append(constant_score_query3)

	payload['query']['filtered']['query']['bool']['should'].append(bool_query)	

	if is_filter:
		bool_query={}
		bool_query['bool']={}
		bool_query['bool']['should']=[]
		for subject in filter_subjects:
			bool_query['bool']['should'].append({'term': {'subject.not_analyzed':subject}})
		for area in filter_areas:
			bool_query['bool']['should'].append({'term': {'area.not_analyzed':area}})
		payload['query']['filtered']['filter']=bool_query

	

	print payload

	print 'http://localhost:9200/local_tutor/teachers/_search?size=10&from='+str(start_from)
	r=requests.post('http://localhost:9200/local_tutor/teachers/_search?size=10&from='+str(start_from),json=payload)
	
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
		if not page or page<1 or page>5:
			page=1

		if not query or query.strip()=='':
			return render_template('search_error.html')

		data={}
		for name,value in dict(request.form).iteritems():
			data[name]=[element.strip() for element in value]
		app.logger.debug(str(data))

		client=MongoClient()
		db=client.local_tutor

		filter_subjects_string=data['subject_selected'][0].split('|')
		
		filter_areas_string=data['areas_selected'][0].split('|')
		
		areas_checkboxes=data['areas_checkboxes'][0].split('|')
		subject_checkboxes=data['subject_checkboxes'][0].split('|')
		filter_subjects=[]
		filter_areas=[]
		is_filter=True

		for subjects in filter_subjects_string:
			if len(subjects)>0:
				
				filter_subjects.append(subjects)
		for areas in filter_areas_string:
			if len(areas)>0:
				
				filter_areas.append(areas)


		print filter_areas
		print filter_subjects

		response=prepare_query(query,(page-1)*10,filter_areas,filter_subjects,is_filter)
		
		


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




		filter_results=False
		if len(areas)>1 or len(subjects)>1:
			filter_results=True


		student_tutor_assoc={}
		if hasattr(current_user,'id'):
			for teacher in paginated_results:
				student_teacher=db.student_tutor.find({'tutor_id':str(teacher['_id']),'student_id':current_user.fb_id}).count()
				if student_teacher>0:
					student_tutor_assoc[teacher['_id']]=True
		print student_tutor_assoc
		total_pages=math.ceil(total/10.0)
		if total_pages>5:
			total_pages=5
		
			
		return render_template('search_result.html',results=paginated_results,query=query,length=(len(paginated_results)+1)/2,
								student_tutor_assoc=student_tutor_assoc,total_pages=total_pages,page=page,filter_results=filter_results,
								areas=areas,subjects=subjects,classify='n')

	query=request.args.get('subject')
	is_classify=request.args.get('classify')
	page=request.args.get('page')
	print page
	
	try:
		page=int(page)
	except Exception,ValueError:
		page=1
	if not page or page<1 or page>5:
		page=1
	if not query or query.strip()=='':
		return render_template('search_error.html')

	print page
	client=MongoClient()
	db=client.local_tutor



	response=prepare_query(query,(page-1)*10,None,None,False)
	
	total=response['hits']['total']
	max_score=response['hits']['max_score']
	results=response['hits']['hits']
	areas=[]
	subjects=[]
	areas_duplicate=[]
	subjects_duplicate=[]
	paginated_results=[]
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

		
	filter_results=False
	if len(areas)>1 or len(subjects)>1:
		filter_results=True


	student_tutor_assoc={}
	if hasattr(current_user,'id'):
		for teacher in paginated_results:
			student_teacher=db.student_tutor.find({'tutor_id':str(teacher['_id']),'student_id':current_user.fb_id}).count()
			if student_teacher>0:
				student_tutor_assoc[teacher['_id']]=True
	print student_tutor_assoc
	total_pages=math.ceil(total/10.0)
	if total_pages>5:
		total_pages=5
		
	return render_template('search_result.html',results=paginated_results,query=query,length=(len(paginated_results)+1)/2,
							student_tutor_assoc=student_tutor_assoc,total_pages=total_pages,page=page,filter_results=filter_results,
							areas=areas,subjects=subjects,classify='n')



		



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

	app.logger.debug(output)
	js=json.dumps(output)
	
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