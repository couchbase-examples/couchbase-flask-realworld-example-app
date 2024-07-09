from flask import Blueprint, request, jsonify, g
from models.comments import Author, Comment
from utils.auth import authenticate
from extensions import couchbase_db
import uuid
from utils.slug import create_slug
from datetime import datetime
from couchbase.exceptions import (
    CouchbaseException,
    DocumentNotFoundException,
)
from validation.common import ErrorResponse
from validation.comments import CreateCommentRequest, CreateCommentResponse, GetCommentsResponse, DeleteCommentResponse
from utils.handle_errors import with_error_handling

comments_blueprint = Blueprint(
    "comments_endpoints",
    __name__,
    url_prefix="/comments",
)


@comments_blueprint.before_request
@with_error_handling()
def apply_authentication_middleware():
    # List of routes that require authentication
    auth_required_routes = ["comments_endpoints.create_comment", "comments_endpoints.get_comments", "comments_endpoints.delete_comment"]

    # Check if the current request endpoint is in the list of routes that require authentication
    if request.endpoint in auth_required_routes:
        response = authenticate()
        if response:
            return response  # Return error response if authentication fails
        

@comments_blueprint.route("/", methods=["POST"])
@with_error_handling()
def create_comment():
    data = CreateCommentRequest(**request.json)
    # TODO : Request Validation
    user = g.current_user
    comment_id = str(uuid.uuid4())
    author = Author (
        following=False,
        bio="",
        image="",
        username=user.username
    )
    try:
            couchbase_db.get_document("articles", data.article_id)
            comment = Comment(
                comment_id=comment_id,
                article_id=data.article_id,
                body=data.body,
                created_at=datetime.utcnow(),
                author=author  # Set author here based on authentication
            )

            couchbase_db.insert_document("comments", comment_id, comment.to_dict())

            return jsonify(CreateCommentResponse(**{"comment": comment.to_dict()}).model_dump()), 201
    
    except DocumentNotFoundException:
            return jsonify(ErrorResponse(**{"message": "Article not found"}).model_dump()), 404
    
    except CouchbaseException as e:
            return jsonify(ErrorResponse(**{"message": "internal server error"}).model_dump()), 500


@comments_blueprint.route("/<article_id>", methods=["GET"])
@with_error_handling()
def get_comments(article_id):
    # Get optional query parameters
    skip = request.args.get("skip", default=0, type=int)
    limit = request.args.get("limit", default=10, type=int)

    comments = couchbase_db.query(f"""SELECT *
        FROM comments
        WHERE article_id = "{article_id}"
        LIMIT {limit} OFFSET {skip}
    """)
    comments_data = []

    for row in comments.rows():
        comment = row['comments']
        comments_data.append(comment)

    # Convert comments to JSON format
    # Return comments as JSON response
    return jsonify(GetCommentsResponse(**{"comments": comments_data}).model_dump()), 200


@comments_blueprint.route("/<comment_id>", methods=["DELETE"])
@with_error_handling()
def delete_comment(comment_id):
    try:
        comment = couchbase_db.get_document("comments", comment_id)
        print("comment 2", comment)

        comment = comment.value
        user = g.current_user  
        if comment["author"]["username"] != user.username:
             return jsonify(ErrorResponse(**{"error": "You don't have permission to delete this comment"}).model_dump()), 403
        print("Comment deleted")
        couchbase_db.delete_document("comments", comment_id)

        return jsonify(DeleteCommentResponse(**{"message": "Comment deleted successfully"}).model_dump()), 200
    
    except DocumentNotFoundException:
            return jsonify(ErrorResponse(**{"message": "Comment not found"}).model_dump()), 404
