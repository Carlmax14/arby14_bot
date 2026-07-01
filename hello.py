name = input("Enter student's name: ")


math = float(input("Enter Mathematics marks: "))
english = float(input("Enter English marks: "))
science = float(input("Enter Science marks: "))
computer = float(input("Enter Computer marks: "))


average = (math + english + science + computer) / 4


if average >= 90:
    grade = "A"
elif average >= 80:
    grade = "B"
elif average >= 70:
    grade = "C"
elif average >= 60:
    grade = "D"
elif average >= 50:
    grade = "E"
else:
    grade = "F"


if average >= 50:
    status = "PASS"
else:
    status = "FAIL"


print("\n------ STUDENT REPORT ------")
print("Student Name:", name)
print("Average:", round(average, 2))
print("Predicted Grade:", grade)
print("Status:", status)