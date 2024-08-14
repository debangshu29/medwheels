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
import logging
from urllib.parse import urlencode
User = get_user_model()




logger = logging.getLogger(__name__)
def ride_map(request, ride_id):
    try:
        # Retrieve the ride object based on the ride ID
        ride = get_object_or_404(Ride, id=ride_id)
    except Ride.DoesNotExist:
        # If the ride doesn't exist, return a 404 error page
        return render(request, 'ride_not_confirmed.html')

    # Check if the ride is confirmed
    if ride.is_confirmed:
        # Check if the ride has been verified (code entered)
        if ride.is_verified:  # Assuming you have an `is_verified` field
            # Redirect to drop map instead of showing the ride map
            return redirect('display_map', ride_id=ride.id)

        # Otherwise, continue with the existing logic for the ride map
        # (This logic remains the same)

        pickup_location = (ride.pickup_latitude, ride.pickup_longitude)

        driver_name = None
        phone_number = None
        license_number = None
        number_plate = None
        ambulance_type = None
        driver_location = None

        if ride.driver:
            try:
                driver_location = DriverLocation.objects.get(driver=ride.driver.user)
            except DriverLocation.DoesNotExist:
                driver_location = None

            driver_name = f"{ride.driver.user.first_name} {ride.driver.user.last_name}"
            phone_number = ride.driver.user.username
            license_number = ride.driver.license_number
            number_plate = ride.driver.number_plate
            ambulance_type = ride.driver.ambulance_type

        if driver_location is None or driver_location.latitude is None or driver_location.longitude is None:
            return HttpResponseBadRequest("Driver location or coordinates are missing")

        if pickup_location[0] is None or pickup_location[1] is None:
            return HttpResponseBadRequest("Pickup location coordinates are missing")

        try:
            driver_latitude = float(driver_location.latitude)
            driver_longitude = float(driver_location.longitude)
            pickup_latitude = float(pickup_location[0])
            pickup_longitude = float(pickup_location[1])
        except TypeError:
            return HttpResponseBadRequest("Invalid coordinates")

        driver_est_time, driver_est_distance = calculate_route(
            (driver_latitude, driver_longitude),
            (pickup_latitude, pickup_longitude)
        )

        if ride.drop_latitude is None or ride.drop_longitude is None:
            return HttpResponseBadRequest("Drop location coordinates are missing")

        try:
            drop_latitude = float(ride.drop_latitude)
            drop_longitude = float(ride.drop_longitude)
        except TypeError:
            return HttpResponseBadRequest("Invalid drop coordinates")

        ride_est_time, ride_est_distance = calculate_route(
            (pickup_latitude, pickup_longitude),
            (drop_latitude, drop_longitude)
        )

        context = {
            'driver_name': driver_name,
            'phone_number': phone_number,
            'license_number': license_number,
            'number_plate': number_plate,
            'ambulance_type': ambulance_type,
            'driver_latitude': driver_latitude,
            'driver_longitude': driver_longitude,
            'pickup_latitude': pickup_latitude,
            'pickup_longitude': pickup_longitude,
            'pickup': ride.pickup,
            'drop': ride.drop,
            'estimated_time': ride_est_time,
            'estimated_distance': ride_est_distance,
            'fare': ride.fare,  # Include the fare in the context
            'driver_est_time': driver_est_time,
            'driver_est_distance': driver_est_distance,
            'ride_id': ride_id
        }

        return render(request, 'ride_map.html', context)
    else:
        messages.error(request, 'Ride is not confirmed yet.')
        return render(request, 'ride_not_confirmed.html')





def ride_not_confirmed(request):
    return render(request, 'ride_not_confirmed.html')


from django.shortcuts import get_object_or_404

def dashboard(request):
    # Assuming the authenticated user is a driver
    if request.user.is_authenticated and request.user.is_driver:
        driver = request.user.driver_profile
        # Assuming you have logic to determine the current ride for the driver
        ride = Ride.objects.filter(driver=driver, is_confirmed=True).last()  # Example to get the last confirmed ride

        context = {
            'driver_name': driver.user.first_name,
            'phone_number': driver.user.username,
            'license_number': driver.license_number,
            'number_plate': driver.number_plate,
            'ambulance_type': driver.ambulance_type,
            'ride_id': ride.id if ride else None  # Pass ride_id to the template
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

            # Calculate the estimated time and distance for the driver to reach the pickup location
            driver_est_time, driver_est_distance = calculate_route(
                (nearest_driver.latitude, nearest_driver.longitude),
                (pickup_lat, pickup_lng)
            )

            # Calculate the estimated time and distance for the ride from pickup to drop-off
            ride_est_time, ride_est_distance = calculate_route(
                (pickup_lat, pickup_lng),
                (drop_lat, drop_lng)
            )

            # Calculate fares
            fare_medbasic = calculate_fare(float(ride_est_distance.split()[0]), 'MedBasic')
            fare_medpro = calculate_fare(float(ride_est_distance.split()[0]), 'MedPro')

            context = {
                'pickup': pickup_address,
                'drop': drop_address,
                'driver_est_time': driver_est_time,
                'driver_est_distance': driver_est_distance,
                'ride_est_time': ride_est_time,
                'ride_est_distance': ride_est_distance,
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


def calculate_route(start_location, end_location):
    # Unpack latitude and longitude from the start and end location tuples
    start_lat, start_lng = start_location
    end_lat, end_lng = end_location

    # Format coordinates without parentheses
    start_str = f"{start_lat},{start_lng}"
    end_str = f"{end_lat},{end_lng}"

    # Replace 'YOUR_API_KEY' with your actual Google Maps API key
    api_key = settings.GOOGLE_MAPS_API_KEY

    # Construct the API request URL
    url = f'https://maps.googleapis.com/maps/api/distancematrix/json?origins={start_str}&destinations={end_str}&key={api_key}'

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
                        print(f"Estimated Time: {estimated_time}, Estimated Distance: {estimated_distance}")
                    else:
                        print("Error in element status:", element['status'])
                        estimated_time = "Not Available"
                        estimated_distance = "Not Available"
                else:
                    print("No elements found")
                    estimated_time = "Not Available"
                    estimated_distance = "Not Available"
            else:
                print("No rows found")
                estimated_time = "Not Available"
                estimated_distance = "Not Available"
        else:
            print("Response status not OK:", data['status'])
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
        required_fields = [
            'pickup', 'drop', 'estimated_time', 'estimated_distance', 'pickup_lat',
            'pickup_lng', 'drop_lat', 'drop_lng', 'ambulance_type', 'fare'
        ]
        if not all(field in request.POST for field in required_fields):
            return HttpResponseBadRequest("Required fields are missing in the request.")

        pickup = request.POST['pickup']
        drop = request.POST['drop']
        pickup_lat = Decimal(request.POST['pickup_lat'])
        pickup_lng = Decimal(request.POST['pickup_lng'])
        drop_lat = Decimal(request.POST['drop_lat'])
        drop_lng = Decimal(request.POST['drop_lng'])
        ambulance_type = request.POST['ambulance_type']
        fare = Decimal(request.POST['fare'])

        # Get driver locations with the specified ambulance type
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

            # Calculate estimated time and distance for the ride from pickup to drop-off
            ride_est_time, ride_est_distance = calculate_route((pickup_lat, pickup_lng), (drop_lat, drop_lng))

            ride = Ride.objects.create(
                driver=driver,
                user=request.user,
                pickup=pickup,
                drop=drop,
                estimated_time=ride_est_time,  # Save estimated time
                estimated_distance=ride_est_distance,  # Save estimated distance
                pickup_latitude=pickup_lat,
                pickup_longitude=pickup_lng,
                drop_latitude=drop_lat,  # Ensure drop coordinates are saved
                drop_longitude=drop_lng,  # Ensure drop coordinates are saved
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
                'estimated_time': ride_est_time,
                'estimated_distance': ride_est_distance,
                'pickup_latitude': pickup_lat,
                'pickup_longitude': pickup_lng,
                'drop_latitude': drop_lat,
                'drop_longitude': drop_lng,
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
        entered_code = request.POST.get('code')
        ride = get_object_or_404(Ride, id=ride_id)

        if entered_code == ride.code:
            # Mark the ride as verified
            ride.is_verified = True
            ride.save()

            return redirect('display_map', ride_id=ride.id)
        else:
            messages.error(request, 'Invalid code. Please try again.')
            return redirect('dashboard')
    else:
        return HttpResponseBadRequest("Invalid request method.")

def check_verification_status(request, ride_id):
    ride = get_object_or_404(Ride, id=ride_id)
    return JsonResponse({'is_verified': ride.is_verified})

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
    ride = get_object_or_404(Ride, id=ride_id)
    pickup_location = (ride.pickup_latitude, ride.pickup_longitude)
    drop_location = (ride.drop_latitude, ride.drop_longitude)

    # Construct the Google Maps URL for navigation from pickup to drop-off
    google_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={pickup_location[0]},{pickup_location[1]}&destination={drop_location[0]},{drop_location[1]}&travelmode=driving"

    # Pass the necessary data to the template for displaying the map
    context = {
        'pickup_location': pickup_location,
        'drop_location': drop_location,
        'google_maps_url': google_maps_url,
        'ride': ride,  # Include ride object to check the user type in the template
        'ride_id': ride_id,
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



def get_driver_location(request, ride_id):
    # Ensure ride exists
    ride = get_object_or_404(Ride, id=ride_id)

    # Ensure there's a driver assigned and that the location is available
    try:
        driver_location = DriverLocation.objects.get(driver=ride.driver.user)
        data = {
            'latitude': driver_location.latitude,
            'longitude': driver_location.longitude
        }
        return JsonResponse(data)
    except DriverLocation.DoesNotExist:
        return JsonResponse({'error': 'Driver location not found'}, status=404)

