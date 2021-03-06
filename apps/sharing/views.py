from urlparse import urlparse
import datetime

from django import forms
from django import http
from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.decorators import login_required 
from django.utils.encoding import force_unicode
from django.http import HttpResponse, HttpResponseRedirect, Http404, HttpResponseForbidden
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.template.defaultfilters import escape
from django.template.loader import render_to_string
from django.template import RequestContext
from django.contrib.gis.geos import Point, Polygon

from django.views.generic.list_detail import object_list, object_detail
from django.shortcuts import render_to_response


from sharing.models import SharedItem
from sharing.forms import SharedForm, SharedFormGET
from location.models import Location
from greenline.utils.location_utils import geocode
from greenline.utils.flickr import *
from greenline.utils.youtube import *

import settings

import logging

log = logging.getLogger("greenline.sharing.views")
console = logging.StreamHandler()
log.addHandler(console)
log.setLevel(logging.DEBUG)

def _get_shared_object(target_object):
    """
    Returns a new (unsaved) shared object.
    """
    new_share = SharedItem(
        content_type = ContentType.objects.get_for_model(target_object),
        object_id    = force_unicode(target_object._get_pk_val()),
        share_date  = datetime.datetime.now(),
    )
    return new_share
        
def render_response(request, *args, **kwargs):
    kwargs['context_instance'] = RequestContext(request)
    return render_to_response(*args, **kwargs)

class SharePostBadRequest(http.HttpResponseBadRequest):
    """
    Response returned when a share post is invalid.
    """
    def __init__(self, why):
        super(SharePostBadRequest, self).__init__()
        if settings.DEBUG:
            self.content = render_to_string("sharing/400-debug.html", {"why": why})

def shares_index(request, username=None, template_name='sharing/shares.html'):
    """
    Return all shared objects.
    
    """
    shares = SharedItem.objects.all()

    return render_to_response(template_name, {
        "shares": shares,
    },context_instance=RequestContext(request))

def share_detail(request, share_id):
    """
    A shared item, in detail.
    
    """
    return object_detail(request, SharedItem.objects.select_related(), object_id=share_id,
        template_object_name='share', template_name='sharing/item.html')

@login_required
def shares_latest(request, username=None, template_name='sharing/shares.html'):
    """
    Return 5 most recent shares.
    
    """
    shares = list(SharedItem.objects.all().order_by("-share_date")[:5])

    return render_to_response(template_name, {
        "shares": shares,
    },context_instance=RequestContext(request))

@login_required
def your_shares(request, template_name="sharing/your_shares.html"):
    """
    Return all shares for this user.
    
    """
    return render_to_response(template_name, {
        "shares": SharedItem.objects.filter(user=request.user),
    }, context_instance=RequestContext(request))

@login_required
def new(request, form_class=SharedForm, success_url=None, 
        extra_context=None, template_name="sharing/new.html"):
    """
    Creates a new shared object.
    
    **Optional arguments:**
    
    ``extra_context``
        A dictionary of variables to add to the template context.
    
    """
    if success_url is None:
        pass
        #success_url = reverse('shares_list_yours', kwargs={ 'username': request.user.username })
        
    if extra_context is None:
        extra_context = {}
    context = RequestContext(request)
                              
    if request.method == "POST" and request.POST["action"] == "create":
        geometry = None
        is_video = False
        is_photo = False
        
        data = request.POST.copy()
                
        comment = data.get("comment")
        station = data.get("station")
        location = data.get("location")
        media = data.get("media").strip('\'"')
        
        if comment:
            pass
        else:
            comment = ''
            #log.debug('comment is %s.', comment)
            
        if station:
            #pass
            log.debug('station is %s.', station)
            
        if media:
            parsed = urlparse(media)
            provider = parsed.netloc.split('.')

            if 'flickr' in provider:
                is_photo = True
                elements = parsed.path.split('/')
                flickr_id = elements[2]
                photo_id = elements[3]

            elif 'youtube' in provider:
                is_video = True
                video_id = parsed.query[2:]

        if media and is_photo:
            if geometry:
                latest = fetch_single_flickr_photo_with_geo(photo_id, flickr_id, geometry, request)
                return HttpResponseRedirect(reverse("shares_list_yours"))
            else:
                latest = fetch_single_flickr_photo(photo_id, flickr_id, request)
                return HttpResponseRedirect(reverse("shares_list_yours"))
                
        if media and is_video:
            if geometry:
                latest = fetch_single_youtube_video_with_geo(video_id, geometry, request)
                return HttpResponseRedirect(reverse("shares_list_yours"))
            else:
                latest = fetch_single_youtube_video(video_id, request)
                return HttpResponseRedirect(reverse("shares_list_yours"))
                
        if location:
            try:
                result = geocode(location)
            except UnboundLocalError:
                return SharePostBadRequest(
                    "Geocoding error for %s ." % escape(result))
            if result:
                geometry = Point(result[1][1], result[1][0])
                loc = Location(author=request.user, address=location, title=result[0], geometry=geometry, description=comment) 
                share = loc.save_as_shared()
                share.save()
                return HttpResponseRedirect(reverse("shares_list_yours"))
            else:
                pass
                #log.debug('we seemed to have failed')
                
        if request.POST["action"] == "create":
            share_form = form_class(request.user, request.POST)
    else:
        if request.method == 'GET':
            share_form = SharedFormGET()

    return render_to_response(template_name, {
        "form": share_form
    }, context_instance=RequestContext(request))