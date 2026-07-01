def length_converter():
    print("\n--- Length Converter ---")
    value = float(input("Enter value in meters: "))
    
    print("1. Meters to Kilometers")
    print("2. Meters to Centimeters")
    print("3. Meters to Millimeters")
    
    choice = input("Choose option: ")
    
    if choice == "1":
        print("Result:", value / 1000, "km")
    elif choice == "2":
        print("Result:", value * 100, "cm")
    elif choice == "3":
        print("Result:", value * 1000, "mm")
    else:
        print("Invalid choice")


def weight_converter():
    print("\n--- Weight Converter ---")
    value = float(input("Enter value in kilograms: "))
    
    print("1. Kilograms to Grams")
    print("2. Kilograms to Pounds")
    
    choice = input("Choose option: ")
    
    if choice == "1":
        print("Result:", value * 1000, "g")
    elif choice == "2":
        print("Result:", value * 2.205, "lbs")
    else:
        print("Invalid choice")


def temperature_converter():
    print("\n--- Temperature Converter ---")
    value = float(input("Enter temperature in Celsius: "))
    
    print("1. Celsius to Fahrenheit")
    print("2. Celsius to Kelvin")
    
    choice = input("Choose option: ")
    
    if choice == "1":
        print("Result:", (value * 9/5) + 32, "°F")
    elif choice == "2":
        print("Result:", value + 273.15, "K")
    else:
        print("Invalid choice")



while True:
    print("\n===== UNIT CONVERTER =====")
    print("1. Length")
    print("2. Weight")
    print("3. Temperature")
    print("4. Exit")

    option = input("Select category: ")

    if option == "1":
        length_converter()
    elif option == "2":
        weight_converter()
    elif option == "3":
        temperature_converter()
    elif option == "4":
        print("Goodbye!")
        break
    else:
        print("Invalid option, try again.")