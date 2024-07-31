from decimal import Decimal
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.db.models import F, FloatField, DecimalField
from django.db.models import F, ExpressionWrapper, FloatField
from django.urls import reverse
from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import DriverLocation, Ride
import json
import requests
from django.db.models import Min, ExpressionWrapper
from django.contrib.auth.decorators import login_required
import googlemaps
from verify.models import CustomUser
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from verify.models import Driver
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.conf import settings
import uuid
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
User = get_user_model()





def ride_map(request, ride_id):
    try:
        # Retrieve the ride object based on the ride ID
        ride = get_object_or_404(Ride, id=ride_id)
    except Ride.DoesNotExist:
        # If the ride doesn't exist, return a 404 error page
        return render(request, 'ride_not_confirmed.html')

    # Check if the ride is confirmed
    if ride.is_confirmed:
        # Retrieve necessary data for rendering the ride map
        pickup_location = (ride.pickup_latitude, ride.pickup_longitude)

        # Initialize driver details to None
        driver_name = None
        phone_number = None
        license_number = None
        number_plate = None
        ambulance_type = None
        driver_location = None

        # Check if the ride has an associated driver
        if ride.driver:
            try:
                driver_location = DriverLocation.objects.get(driver=ride.driver.user)
            except DriverLocation.DoesNotExist:
                pass

            driver_name = f"{ride.driver.user.first_name} {ride.driver.user.last_name}"
            phone_number = ride.driver.user.username
            license_number = ride.driver.license_number
            number_plate = ride.driver.number_plate
            ambulance_type = ride.driver.ambulance_type

        # Pass necessary data to the template
        context = {
            'driver_name': driver_name,
            'phone_number': phone_number,
            'license_number': license_number,
            'number_plate': number_plate,
            'ambulance_type': ambulance_type,
            'driver_latitude': driver_location.latitude if driver_location else None,
            'driver_longitude': driver_location.longitude if driver_location else None,
            'pickup_latitude': pickup_location[0],
            'pickup_longitude': pickup_location[1],
            'pickup': ride.pickup,
            'drop': ride.drop,
            'estimated_time': ride.estimated_time,
            'estimated_distance': ride.estimated_distance,
            'fare': ride.fare,  # Include the fare in the context
        }

        return render(request, 'ride_map.html', context)
    else:
        # If the ride is not confirmed, display a message and redirect
        messages.error(request, 'Ride is not confirmed yet.')
        return render(request, 'ride_not_confirmed.html')

def ride_not_confirmed(request):
    return render(request, 'ride_not_confirmed.html')


def dashboard(request):
    # Assuming the authenticated user is a driver
    if request.user.is_authenticated and request.user.is_driver:
        driver = request.user.driver_profile
        context = {
            'driver_name': driver.user.first_name,
            'phone_number': driver.user.username,
            'license_number': driver.license_number,
            'number_plate': driver.number_plate,
            'ambulance_type': driver.ambulance_type
        }
        return render(request, 'dashboard.html', context)
    else:
        # Redirect to login or handle unauthorized access
        return render(request, 'unauthorized.html')


@csrf_exempt
def update_location(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            location_name = data.get('location_name')

            # Validate received data (you may add more validations as per your requirements)
            if latitude is None or longitude is None:
                return JsonResponse({'error': 'Latitude or longitude missing'}, status=400)

            # Assuming the driver is authenticated, you can get the driver from the request
            driver = request.user  # Assuming the authenticated user is a driver

            # Update or create DriverLocation
            driver_location, created = DriverLocation.objects.update_or_create(
                driver=driver,
                defaults={
                    'latitude': latitude,
                    'longitude': longitude,
                    'location_name': location_name
                }
            )

            # You can return any additional data you want to the frontend
            return JsonResponse({'success': True, 'message': 'Location updated successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Only POST requests are allowed'}, status=405)




def service_view(request):
    # Fetch all driver locations from the database
    locations = DriverLocation.objects.all()


    # Pass the locations to the template
    return render(request, 'service.html', {'locations': locations})


def calculate_fare(distance, ambulance_type):
    base_fare = 50.0
    per_km_rate = 10.0
    if ambulance_type == 'MedPro':
        base_fare += 20.0  # Additional base fare for MedPro
        per_km_rate += 5.0  # Additional per km rate for MedPro
    return base_fare + (per_km_rate * distance)

def address_to_coordinates(address):
    gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
    geocode_result = gmaps.geocode(address)
    if geocode_result and 'geometry' in geocode_result[0] and 'location' in geocode_result[0]['geometry']:
        location = geocode_result[0]['geometry']['location']
        return location['lat'], location['lng']
    else:
        return None, None


def get_distance_matrix(origins, destinations):
    gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
    matrix = gmaps.distance_matrix(origins, destinations, mode="driving")
    return matrix


def dijkstra_algorithm(graph, start_node):
    unvisited_nodes = list(graph.keys())
    shortest_path = {}
    previous_nodes = {}
    max_value = float('inf')

    for node in unvisited_nodes:
        shortest_path[node] = max_value
    shortest_path[start_node] = 0

    while unvisited_nodes:
        current_min_node = None
        for node in unvisited_nodes:
            if current_min_node is None:
                current_min_node = node
            elif shortest_path[node] < shortest_path[current_min_node]:
                current_min_node = node

        neighbors = graph[current_min_node].items()
        for neighbor, weight in neighbors:
            tentative_value = shortest_path[current_min_node] + weight
            if tentative_value < shortest_path[neighbor]:
                shortest_path[neighbor] = tentative_value
                previous_nodes[neighbor] = current_min_node

        unvisited_nodes.remove(current_min_node)

    return previous_nodes, shortest_path
def ride_view(request):
    if request.method == 'POST':
        pickup_address = request.POST.get('pickup')
        drop_address = request.POST.get('drop')

        # Convert addresses to coordinates
        pickup_lat, pickup_lng = address_to_coordinates(pickup_address)
        drop_lat, drop_lng = address_to_coordinates(drop_address)

        if pickup_lat is not None and pickup_lng is not None and drop_lat is not None and drop_lng is not None:
            driver_locations = DriverLocation.objects.all()
            if not driver_locations:
                return HttpResponseBadRequest("No drivers available.")

            origins = [(float(pickup_lat), float(pickup_lng))]
            destinations = [(float(driver.latitude), float(driver.longitude)) for driver in driver_locations]

            matrix = get_distance_matrix(origins, destinations)

            graph = {}
            graph[(float(pickup_lat), float(pickup_lng))] = {}
            for i, element in enumerate(matrix['rows'][0]['elements']):
                distance = element['distance']['value']
                driver_location = (float(driver_locations[i].latitude), float(driver_locations[i].longitude))
                graph[(float(pickup_lat), float(pickup_lng))][driver_location] = distance
                graph[driver_location] = {}  # Initialize the driver's location in the graph

            previous_nodes, shortest_path = dijkstra_algorithm(graph, (float(pickup_lat), float(pickup_lng)))

            nearest_driver = None
            min_distance = float('inf')
            for driver in driver_locations:
                driver_node = (float(driver.latitude), float(driver.longitude))
                if driver_node in shortest_path and shortest_path[driver_node] < min_distance:
                    min_distance = shortest_path[driver_node]
                    nearest_driver = driver

            # Use the correct function for distance and time calculation
            estimated_time, estimated_distance = calculate_route((nearest_driver.latitude, nearest_driver.longitude), (pickup_lat, pickup_lng))
            fare_medbasic = calculate_fare(float(estimated_distance.split()[0]), 'MedBasic')
            fare_medpro = calculate_fare(float(estimated_distance.split()[0]), 'MedPro')

            context = {
                'pickup': pickup_address,
                'drop': drop_address,
                'estimated_time': estimated_time,
                'estimated_distance': estimated_distance,
                'pickup_lat': pickup_lat,
                'pickup_lng': pickup_lng,
                'drop_lat': drop_lat,
                'drop_lng': drop_lng,
                'fare_medbasic': fare_medbasic,
                'fare_medpro': fare_medpro,
                'nearest_driver': nearest_driver  # Pass the nearest driver to the template
            }

            return render(request, 'service1.html', context)
        else:
            return HttpResponseBadRequest("Invalid pickup or drop address.")

    return render(request, 'service1.html')


def calculate_route(driver_location, pickup_location):
    # Unpack latitude and longitude from the driver_location tuple
    driver_lat, driver_lng = driver_location

    # Unpack pickup latitude and longitude from the pickup_location tuple
    pickup_lat, pickup_lng = pickup_location

    # Format coordinates without parentheses
    pickup_str = f"{pickup_lat},{pickup_lng}"
    driver_str = f"{driver_lat},{driver_lng}"

    # Replace 'YOUR_API_KEY' with your actual Google Maps API key
    api_key = 'AIzaSyAvSl8hKmXkz9tE8ctzuXtRQz0Y2lUFknI'

    # Construct the API request URL
    url = f'https://maps.googleapis.com/maps/api/distancematrix/json?origins={pickup_str}&destinations={driver_str}&key={api_key}'

    print("API Request URL:", url)  # Print API request URL for debugging

    try:
        # Send a GET request to the API
        response = requests.get(url)
        data = response.json()

        print("API Response:", data)  # Print the API response for debugging

        # Check if response status is OK
        if data['status'] == 'OK':
            # Extract estimated time and distance from the API response
            rows = data.get('rows', [])
            if rows:
                elements = rows[0].get('elements', [])
                if elements:
                    element = elements[0]
                    if element['status'] == 'OK':
                        estimated_time = element.get('duration', {}).get('text')
                        estimated_distance = element.get('distance', {}).get('text')
                    else:
                        estimated_time = "Not Available"
                        estimated_distance = "Not Available"
                else:
                    estimated_time = "Not Available"
                    estimated_distance = "Not Available"
            else:
                estimated_time = "Not Available"
                estimated_distance = "Not Available"
        else:
            estimated_time = "Not Available"
            estimated_distance = "Not Available"

    except Exception as e:
        # Handle API request errors
        print(f'Error: {e}')
        estimated_time = "Not Available"
        estimated_distance = "Not Available"

    return estimated_time, estimated_distance





@transaction.atomic
def save_booking_view(request):
    if request.method == 'POST':
        required_fields = ['pickup', 'drop', 'estimated_time', 'estimated_distance', 'pickup_lat', 'pickup_lng', 'ambulance_type', 'fare']
        if not all(field in request.POST for field in required_fields):
            return HttpResponseBadRequest("Required fields are missing in the request.")

        pickup = request.POST['pickup']
        drop = request.POST['drop']
        estimated_time = request.POST['estimated_time']
        estimated_distance = request.POST['estimated_distance']
        pickup_lat = Decimal(request.POST['pickup_lat'])
        pickup_lng = Decimal(request.POST['pickup_lng'])
        ambulance_type = request.POST['ambulance_type']
        fare = Decimal(request.POST['fare'])

        driver_locations = DriverLocation.objects.filter(driver__driver_profile__ambulance_type=ambulance_type)

        if not driver_locations:
            messages.error(request, 'No available drivers with the specified ambulance type. Please try again later.')
            return render(request, 'service1.html')

        origins = [(pickup_lat, pickup_lng)]
        destinations = [(driver.latitude, driver.longitude) for driver in driver_locations]

        matrix = get_distance_matrix(origins, destinations)

        graph = {(pickup_lat, pickup_lng): {}}
        for i, driver_location in enumerate(driver_locations):
            driver_node = (driver_location.latitude, driver_location.longitude)
            distance = matrix['rows'][0]['elements'][i]['distance']['value']  # distance in meters
            distance_km = distance / 1000.0  # convert to kilometers
            graph[(pickup_lat, pickup_lng)][driver_node] = distance_km
            graph[driver_node] = {}

        previous_nodes, shortest_paths = dijkstra_algorithm(graph, (pickup_lat, pickup_lng))
        nearest_driver_node = min(shortest_paths, key=lambda k: shortest_paths[k] if k != (pickup_lat, pickup_lng) else float('inf'))
        nearest_driver = driver_locations.get(latitude=nearest_driver_node[0], longitude=nearest_driver_node[1])

        if nearest_driver:
            driver = nearest_driver.driver.driver_profile

            ride = Ride.objects.create(
                driver=driver,
                user=request.user,
                pickup=pickup,
                drop=drop,
                estimated_time=estimated_time,
                estimated_distance=estimated_distance,
                pickup_latitude=pickup_lat,
                pickup_longitude=pickup_lng,
                ambulance_type=ambulance_type,
                fare=fare,
                is_confirmed=False
            )

            ride.token = generate_unique_token()
            ride.save()

            send_ride_request_email(request, ride)

            messages.success(request, 'Booking requested successfully. Waiting for driver confirmation.')

            return render(request, 'booking_success.html', {
                'ride_id': ride.id,
                'pickup': pickup,
                'drop': drop,
                'estimated_time': estimated_time,
                'estimated_distance': estimated_distance,
                'pickup_latitude': pickup_lat,
                'pickup_longitude': pickup_lng,
                'fare': fare,
                'ambulance_type': ambulance_type,
                'driver_latitude': nearest_driver_node[0],
                'driver_longitude': nearest_driver_node[1],
                'driver_name': driver.user.first_name + ' ' + driver.user.last_name,
                'phone_number': driver.user.username,
                'license_number': driver.license_number,
                'number_plate': driver.number_plate
            })
        else:
            messages.error(request, 'No available drivers. Please try again later.')
            return redirect('service1')

    return HttpResponseBadRequest("Invalid request method.")
def booking_success(request):
    # Check if the booking request is sent and confirmed
    if request.session.get('ride_confirmed'):
        # If the ride is confirmed, redirect to ride_map
        ride_id = request.session.get('ride_id')
        if ride_id:
            return redirect('ride_map', ride_id=ride_id)
    else:
        # If the ride is not confirmed, render the booking success page
        return render(request, 'booking_success.html')





def generate_unique_token():
    # Generate a unique token for ride confirmation
    return uuid.uuid4().hex[:16]

def send_ride_request_email(request, ride):
    # Construct the accept and reject URLs with the token
    accept_url = request.build_absolute_uri(f'/accept-ride-by-email/?token={ride.token}')
    reject_url = request.build_absolute_uri(f'/reject-ride-by-email/?token={ride.token}')

    # Render the email template with context
    context = {
        'pickup': ride.pickup,
        'drop': ride.drop,
        'estimated_time': ride.estimated_time,
        'estimated_distance': ride.estimated_distance,
        'accept_url': accept_url,
        'reject_url': reject_url,
    }
    email_html_message = render_to_string('ride_request_email.html', context)
    plain_message = strip_tags(email_html_message)

    # Send the email
    subject = 'New Ride Request'
    sender = settings.EMAIL_HOST_USER  # Your Gmail email address
    recipient = ride.driver.user.email  # Driver's email address

    send_mail(
        subject,
        plain_message,
        sender,
        [recipient],
        html_message=email_html_message,
    )


def accept_ride_by_email(request):
    if request.method == 'GET':
        token = request.GET.get('token')

        # Try to retrieve the ride object associated with the token
        ride = Ride.objects.filter(token=token).first()

        if ride:
            # If the ride exists, update its status to 'confirmed'
            ride.is_confirmed = True
            ride.save()
            send_code_to_user(ride.id, ride.code)
            # Set session variable to indicate ride confirmation
            request.session['ride_confirmed'] = True

            # Send notification to the user (passenger) confirming the ride
            # Implement your notification logic here
            return redirect('ride_map', ride_id=ride.id)
        else:
            messages.error(request, 'Invalid token or ride already confirmed.')
            return redirect('dashboard')
    else:
        return HttpResponseBadRequest("Invalid request method.")

def driver_reject(request):
    return render(request,'driver_reject.html')

def reject_ride_by_email(request):
    if request.method == 'GET':
        token = request.GET.get('token')

        # Try to retrieve the ride object associated with the token
        ride = Ride.objects.filter(token=token).first()

        if ride:
            # If the ride exists, delete it from the database or update its status to indicate rejection
            ride.delete()  # You can adjust this to update status instead of deleting

            messages.info(request, 'Ride rejected via email. Booking not confirmed.')

            return render(request, 'driver_reject.html')  # Redirect back to the driver reject page after rejecting the ride via email
        else:
            messages.error(request, 'Invalid token or ride not found.')
            return redirect('dashboard')
    else:
        return HttpResponseBadRequest("Invalid request method.")


def verify_code(request, ride_id):
    if request.method == 'POST':
        # Get the code entered by the driver
        entered_code = request.POST.get('code')

        # Retrieve the ride
        ride = Ride.objects.get(id=ride_id)

        # Check if the entered code matches the one associated with the ride
        if entered_code == ride.code:
            # If the code is correct, display the map
            return redirect('display_map', ride_id=ride_id)
        else:
            # If the code is incorrect, display an error message
            messages.error(request, 'Invalid code. Please try again.')
            return redirect('dashboard')  # Redirect back to the dashboard
    else:

        return HttpResponseBadRequest("Invalid request method.")

def generate_and_send_code(request, ride_id):
    try:
        # Retrieve the ride object
        ride = Ride.objects.get(id=ride_id)
    except Ride.DoesNotExist:
        # Handle the case where the ride object does not exist
        return HttpResponseBadRequest("Invalid ride ID.")

    # Generate a unique 4-digit code
    code = generate_unique_4_digit_code()

    # Associate the code with the ride
    ride.pickup_code = code
    ride.save()

    # Send the code to the user (send via email, SMS, etc.)
    send_code_to_user(ride.user.email, code)

    # Generate the URL for the verify_code view
    url = reverse('verify_code', kwargs={'ride_id': ride_id})  # Pass the ride_id parameter

    # Render a page indicating that the code is sent
    return render(request, 'code_sent.html', {'verification_url': request.build_absolute_uri(url)})




def display_map(request, ride_id):
    # Retrieve the ride and necessary details for displaying the map
    ride = Ride.objects.get(id=ride_id)
    pickup_location = (ride.pickup_latitude, ride.pickup_longitude)
    drop_location = (ride.drop_latitude, ride.drop_longitude)

    # Pass the necessary data to the template for displaying the map
    context = {
        'pickup_location': pickup_location,
        'drop_location': drop_location,
        # Other necessary data for displaying the map
    }
    return render(request, 'drop_map.html', context)

def generate_unique_4_digit_code():
    """
    Generate a unique 4-digit code.
    """
    return uuid.uuid4().hex[:4].upper()


def send_code_to_user(ride_id, code):
    """
    Send the generated code to the user via email.
    """
    try:
        # Retrieve the ride object
        ride = Ride.objects.get(id=ride_id)
    except Ride.DoesNotExist:
        # Handle the case where the ride object does not exist
        print("Ride does not exist.")
        return

    # Check if ride has a user associated with it
    if not ride.user:
        print("Ride does not have a user associated with it.")
        return

    # Check if the user has a valid email address
    user_email = ride.user.email
    if not user_email:
        print("User does not have a valid email address.")
        return

    subject = 'Your Pickup Code'
    message = f'Your pickup code is: {code}'
    sender = settings.EMAIL_HOST_USER

    # Print debug statements
    print(f"Sending email to: {user_email}")
    print(f"Email content: {message}")

    # Send the email
    send_mail(subject, message, sender, [user_email])

    print("Email sent successfully.")

