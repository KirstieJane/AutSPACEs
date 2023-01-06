import datetime
import io
import json
import logging
import uuid

import requests
from django.conf import settings
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from openhumans.models import OpenHumansMember

from .models import PublicExperience

from .forms import ShareExperienceForm

logger = logging.getLogger(__name__)


def index(request):
    """
    Starting page for app.
    """
    auth_url = OpenHumansMember.get_auth_url()
    context = {'auth_url': auth_url,
               'oh_proj_page': settings.OH_PROJ_PAGE}
    if request.user.is_authenticated:
        return redirect('main:overview')
    return render(request, 'main/home.html', context=context)


def overview(request):
    if request.user.is_authenticated:
        oh_member = request.user.openhumansmember
        context = {'oh_id': oh_member.oh_id,
                   'oh_member': oh_member,
                   'oh_proj_page': settings.OH_PROJ_PAGE}
        return render(request, 'main/home.html', context=context)
    return redirect('index')


def logout_user(request):
    """
    Logout user
    """
    if request.user.is_authenticated:
        logout(request)
    return redirect('index')

def share_experience(request, edit=False):
    # if this is a POST request we need to process the form data
    if request.user.is_authenticated: 
        
        if request.method == 'POST':
            # create a form instance and populate it with data from the request:
            form = ShareExperienceForm(request.POST)
            # check whether it's valid:
            if edit:
                # if edit=True, we render the share_experiences.html with form prepopulated.
                return render(request, 'main/share_experiences.html', {'form': form})    
            else:
                # if edit=False, we proceed to submission.
                if form.is_valid():
                    
                    # make a new uuid if doesn't already exist.
                    uuid = form.cleaned_data.pop("uuid", False)
                    
                    if uuid: 
                        # we will be here if we are editing a record already exists               

                        # for OH we need to Delete before reupload.
                        request.user.openhumansmember.delete_single_file(file_id = form.cleaned_data.pop("file_id"))
                        
                        #TODO:above line is hack, should remove file_id from form and make a function file_id_from_uuid(uuid = uuid, ohmember=request.user.openhumansmember))
                    
                    else:
                        uuid = make_uuid()
                        
                    upload(data = form.cleaned_data, uuid = uuid, ohmember = request.user.openhumansmember)                
                    
                    # for Public Experience we need to check if it's viewable and update accordingly.
                    update_public_experience_db(data=form.cleaned_data, uuid=uuid, ohmember=request.user.openhumansmember)                
                    
                    # redirect to a new URL:
                    return redirect('main:confirm_page')

        # if a GET (or any other method) we'll create a blank form
        else:
            form = ShareExperienceForm()
    
    else:    
        return redirect('index')

def update_public_experience_db(data, uuid, ohmember, moderation_status = 'in review'):
    """Updates the public experience database for the given uuid.
    
    If data is tagged as viewable, an experience will be updated or inserted.
    If a data is tagged as not public, this function ensures that it is absent from the pe db.

    Args:
        data (dict): an experience
        uuid (str): unique identifier
        ohmember : request.user.openhumansmember
        moderation_status (str, optional): Defaults to 'in review'.
    """
    
    if data['viewable']:
        
        pe = PublicExperience(experience_text=data['experience'],
            difference_text=data['wish_different'],
            title_text=data['title'],
            open_humans_member=ohmember,
            experience_id=uuid,
            abuse=data['abuse'],
            violence=data['violence'],
            drug=data['drug'],
            mentalhealth=data['mentalhealth'],
            negbody=data['negbody'],
            other=True if data['other'] != '' else False,
            approved='not reviewed'
        )
        
        # .save() updates if primary key exists, inserts otherwise. 
        pe.save()        
        
    else:
        delete_PE(uuid,ohmember)
        
            
def delete_PE(uuid, ohmember):
    if PublicExperience.objects.filter(experience_id=uuid, open_humans_member=ohmember).exists():
            PublicExperience.objects.get(experience_id=uuid, open_humans_member=ohmember).delete()
    
def make_uuid():
    return str(uuid.uuid1())

def upload(data, uuid, ohmember):
    """Uploads a dictionary representation of an experience to open humans.

    Args:
        data (dict): an experience
        uuid (str): unique identifier
        ohmember : request.user.openhumansmember
    """
    
    output_json = {
            'data': data,
            'timestamp': str(datetime.datetime.now())}
    
    # by saving the output json into metadata we can access the fields easily through request.user.openhumansmember.list_files().
    metadata = {
        'uuid': uuid,   
        'description': data.get('title'),
        'tags': make_tags(data),
        **output_json,
        }
    
    # create stream for oh upload
    output = io.StringIO()
    output.write(json.dumps(output_json))
    output.seek(0)
            

    ohmember.upload(
        stream=output,
        filename=f"{'_'.join((data.get('title')).lower().split()[:2])}_{str(datetime.datetime.now().isoformat(timespec='seconds'))}.json", #filename is Autspaces_timestamp
        metadata=metadata)

def make_tags(data):
    """builds list of tags based on data"""
    
    tag_map = {'viewable': {'True':'public',
                            'False':'not public'},
               'research': {'True':'research',
                            'False':'non-research'},
                'drug':    {'True': 'drugs',
                            'False': ''},
                'abuse':    {'True': 'abuse',
                            'False': ''},
                'negbody':  {'True': 'negative body',
                            'False': ''},
                'violence': {'True': 'violence',
                            'False': ''},
                'mentalhealth': {'True': 'mental health',
                            'False': ''},
                'moderation_status': {'True': '',
                            'False': 'in review'}
                            }
    
    tags = [tag_map[k].get(str(v)) 
            for k,v in data.items() 
            if k in tag_map.keys()]
    if data["other"] != '':
        tags.append("Other triggering label")
    
    return tags
    
def delete_experience(request, confirmed=False):
    if request.user.is_authenticated:
    
        file_id = request.POST.get("file_id")
        uuid = request.POST.get("uuid")
        title = request.POST.get("title")
        
        if confirmed:   
            delete_single_file(file_id = file_id,
                               uuid = uuid,
                               ohmember = request.user.openhumansmember)
            
                
            return render(request, 'main/deletion_success.html', {"title":title})
        
        else:
            return render(request, 'main/deletion_confirmation.html', {"title": title,
                                                                       "file_id": file_id,
                                                                       "uuid": uuid})
    else:    
        return redirect('index')
        
    
def delete_single_file(file_id, uuid, ohmember):
    """Deletes a given file id and uuid from openhumans and ensures absence from local PublicExperiences database.

    Args:
        file_id (str): openhumans file id
        uuid (str | bool): Either a uuid for the PublicExperience field 'experience id', or False if entry non-existent. 
        ohmember : request.user.openhumansmember
    """

    ohmember.delete_single_file(file_id=file_id)
    delete_PE(uuid,ohmember)
    

def list_files(request):
    if request.user.is_authenticated:
        context = {'files': request.user.openhumansmember.list_files()}
        return render(request, 'main/list.html',
                      context=context)
    return redirect('index')


def list_public_experiences(request):
    # experiences = PublicExperience.objects.filter(approved='approved')
    experiences = PublicExperience.objects.all()

    return render(
        request,
        'main/experiences_page.html',
        context={'experiences': experiences})


def moderate_public_experiences(request):
    experiences = PublicExperience.objects.filter(approved='not reviewed')
    return render(
        request,
        'main/moderate_public_experiences.html',
        context={'experiences': experiences})


def review_experience(request, experience_id):
    experience = PublicExperience.objects.get(experience_id=experience_id)
    print(experience)
    experience.approved = 'approved'
    experience.save()
    print(experience.approved)
    return redirect('moderate_public_experiences')


def make_non_viewable(request, oh_file_id, file_uuid):
    pe = PublicExperience.objects.get(experience_id=file_uuid)
    pe.delete()
    oh_files = request.user.openhumansmember.list_files()
    for f in oh_files:
        if str(f['id']) == str(oh_file_id):
            experience = requests.get(f['download_url']).json()
            new_metadata = f['metadata']
            new_metadata['tags'] = ['not public'] + f['metadata']['tags'][1:]
            output = io.StringIO()
            output.write(json.dumps(experience))
            output.seek(0)
            request.user.openhumansmember.upload(
                stream=output,
                filename='testfile.json',
                metadata=new_metadata)
            request.user.openhumansmember.delete_single_file(file_id=oh_file_id)
    return redirect('main:list')


def make_viewable(request, oh_file_id, file_uuid):
    oh_files = request.user.openhumansmember.list_files()
    for f in oh_files:
        if str(f['id']) == str(oh_file_id):
            experience = requests.get(f['download_url']).json()
            new_metadata = f['metadata']
            new_metadata['tags'] = ['viewable'] + f['metadata']['tags'][1:]
            output = io.StringIO()
            output.write(json.dumps(experience))
            output.seek(0)
            request.user.openhumansmember.upload(
                stream=output,
                filename='testfile.json',
                metadata=new_metadata)
            request.user.openhumansmember.delete_single_file(
                file_id=oh_file_id)
            PublicExperience.objects.create(
                experience_text=experience['text'],
                difference_text=experience['wish_different'],
                open_humans_member=request.user.openhumansmember,
                experience_id=file_uuid)
    return redirect('list')


def make_non_research(request, oh_file_id, file_uuid):
    oh_files = request.user.openhumansmember.list_files()
    for f in oh_files:
        if str(f['id']) == str(oh_file_id):
            experience = requests.get(f['download_url']).json()
            new_metadata = f['metadata']
            new_metadata['tags'] = f['metadata']['tags'][:-1] + ['non-research']
            output = io.StringIO()
            output.write(json.dumps(experience))
            output.seek(0)
            request.user.openhumansmember.upload(
                stream=output,
                filename='testfile.json',
                metadata=new_metadata)
            request.user.openhumansmember.delete_single_file(
                file_id=oh_file_id)
    return redirect('list')


def make_research(request, oh_file_id, file_uuid):
    oh_files = request.user.openhumansmember.list_files()
    for f in oh_files:
        if str(f['id']) == str(oh_file_id):
            experience = requests.get(f['download_url']).json()
            new_metadata = f['metadata']
            new_metadata['tags'] = f['metadata']['tags'][:-1] + ['research']
            output = io.StringIO()
            output.write(json.dumps(experience))
            output.seek(0)
            request.user.openhumansmember.upload(
                stream=output,
                filename='testfile.json',
                metadata=new_metadata)
            request.user.openhumansmember.delete_single_file(
                file_id=oh_file_id)
    return redirect('list')

def edit_experience(request):

    print(request.POST)
    return render(request, 'main/share_experiences.html')

    # context = {}
    # if request.method == 'POST':
    #     print(request.POST)
    #     return render(request, 'main/share_experiences.html', context)
    # else:
    #     if request.user.is_authenticated:
    #         return render(request, 'main/share_experiences.html', context)
    # redirect('main:my_stories')

def signup(request):
    return render(request, "main/signup.html")

def registration(request):
    registration_status = True
    print(registration_status)
    return render(request, "main/registration.html", {'page_status': 'registration'})

def signup_frame4_test(request):
    return render(request, "main/signup1.html")

def my_stories(request):
    if request.user.is_authenticated:
        context = {'files': request.user.openhumansmember.list_files()}
        return render(request, "main/my_stories.html", context)
    else:
        return redirect("main:overview")


def confirmation_page(request):
    """
    Confirmation Page For App
    """
    return render(request, "main/confirmation_page.html")


def about_us(request):
    return render(request, "main/about_us.html")

# def what_autism_is(request):
#     auth_url = OpenHumansMember.get_auth_url()
#     context = {'auth_url': auth_url,
#                'oh_proj_page': settings.OH_PROJ_PAGE}
#     if request.user.is_authenticated:
#         return redirect('main:what_autism_is')
#     return render(request, 'main/what_autism_is.html', context=context)
def navigation(request):
    return render(request, "main/navigation.html")

# def about_us(request):
#     return render(request, "main/about_us.html")

def what_autism_is(request):
    return render(request, "main/what_autism_is.html")

def footer(request):
    return render(request, "main/footer.html")

