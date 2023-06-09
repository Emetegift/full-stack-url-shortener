import re
from ..models import Link
from flask_smorest import abort, Blueprint
from flask import redirect, make_response, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask.views import MethodView
from ..schemas import LinkSchema, GetLinksSchema
from ..utils.validate_url import validate_url
from ..utils import check_if_user_is_still_logged_in
from ..extensions import db, cache
from flask import request
import re
import string
import random

blp = Blueprint("urls", __name__, description="Operations on URLS")

@blp.route("/short-urls")
class CreateShortUrl(MethodView):
    @blp.arguments(LinkSchema)
    @jwt_required()  # Requires a valid access token for access
    def post(self, new_url):
        """Create a new short URL"""
        current_user = get_jwt_identity()  # Get the current user's id from the JWT
        url_pattern = r'https'  # Required URL pattern

        if not re.match(url_pattern, new_url["original_url"]):
            # Check if the original URL matches the required pattern
            abort(400, message="Invalid URL format")

        if not new_url["original_url"].startswith('http://') and not new_url["original_url"].startswith('https://'):
            # Prepend 'http://' to the original URL if it doesn't start with 'http://' or 'https://'
            new_url["original_url"] = 'http://' + new_url["original_url"]

        if "custom_url" in new_url:
            # Customization logic for short URL
            custom_url = new_url["custom_url"]
            if custom_url and not custom_url.isalnum() and '_' not in custom_url and '-' not in custom_url:
                # Check if the custom URL format is valid
                abort(400, message="Invalid custom URL format")

            existing_link = Link.query.filter_by(short_url=custom_url).first()
            if existing_link:
                # Check if the custom URL is already taken
                abort(400, message="Custom URL is already taken")
        else:
            generated_url = self.generate_random_short_url()
            existing_link = Link.query.filter_by(short_url=generated_url).first()
            while existing_link:
                # Generate a random short URL and check if it's already taken
                generated_url = self.generate_random_short_url()
                existing_link = Link.query.filter_by(short_url=generated_url).first()

            new_url["short_url"] = generated_url

        link = Link(**new_url)  # Create a new Link object with the provided data
        link.save()  # Save the link object to the database

        response = {
            "original_url": link.original_url,
            "shortened_url": f"{request.host_url}{link.short_url}",
        }
        return response, 201

    def generate_random_short_url(self):
        length = 6  # Length of the random short URL
        characters = string.ascii_letters + string.digits  # Characters to choose from
        return ''.join(random.choice(characters) for _ in range(length))

@blp.route("/<short_url>")
class RedirectShortUrl(MethodView):
    @blp.response(302)  # Set the response status code to 302 (redirect)
    @cache.memoize(timeout=3600)  # Cache the response for 3600 seconds (1 hour)
    def get(self, short_url):
        """Redirect to the original URL and update view count"""
        link = Link.query.filter_by(short_url=short_url).first()
        if not link:
            # Check if the link with the provided short URL exists
            abort(404, message="URL not found")

        link.analytics += 1  # Increment the view count of the link
        db.session.commit()  # Save the changes to the database

        return redirect(link.original_url)  # Redirect to the original URL
    
    
    

@blp.route("/<short_url>/qr-code")
@jwt_required()  # Requires a valid access token for access
@cache.cached(timeout=3600)  # Cache the response for 3600 seconds (1 hour)
def qr_code(short_url):
    """Get the QR code for a short URL"""
    link = Link.query.filter_by(short_url=short_url).first_or_404()
    if not link.qr_code:
        # If the QR code hasn't been generated yet, generate it now
        link.qr_code = link.generate_qr_code()
        link.save()

    response = make_response(link.qr_code)  # Create a response with the QR code image
    response.headers.set("Content-Type", "image/jpeg")  # Set the response content type to JPEG image
    return response


@blp.route("/all-links")
@blp.response(200, LinkSchema(many=True))  # Specify the response schema
@jwt_required()  # Requires a valid access token for access
@cache.cached(timeout=3600)  # Cache the response for 3600 seconds (1 hour)
def get_links():
    
    current_user = get_jwt_identity()  # Get the current user's id from the JWT
    links = Link.query.filter_by(user_id=current_user).all()  # Fetch all links belonging to the user
    
    if links:
     serialized_links = LinkSchema(many=True).dump(links)  # Serialize the links      
     return serialized_links, 200
    else:
        return {"message": "No links found for the user."}, 404
