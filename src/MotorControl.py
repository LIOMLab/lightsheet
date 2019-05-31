import serial
from commandGenerator import*

def main():

    #rtscts est lie au handshake?
    ser = serial.Serial(port='COM3', baudrate=9600,bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE) #rtscts=True
    print(ser.name)
    print(ser.is_open)


    #On deplace a la position minimale
    commande=bytearray([1,20,0,0,0,0])
    ser.write(commande)
    replyData1=ser.read(6)  #Permet aussi que la commande precedente soit terminee avant la prochaine


    #On deplace a la position maximale
    commande=bytearray([1,20,85,35,8,0])
    ser.write(commande)
    replyData2=ser.read(6)



    #On deplace relativement de -10 000 microsteps, le reply Data est la position absolue resultante
    commande=bytearray([1,21,240,216,255,255])
    ser.write(commande)
    replyData3=ser.read(6)


    #Retourne l'ID du moteur 6320
    commande = bytearray([1,50,0,0,0,0])
    ser.write(commande)

    arr=range(6)
    replyData4=[]
    for i in arr:
        replyData4.append(bytes2int(ser.read(1)))

    print("La reponse renvoyee sous la forme d'une commande est: {}".format(replyData4))
    print("L'ID du moteur T-LSM100B est 6320, celui renvoye par le programme est: {} \n".format(replyCommand2Data(replyData4)))


    #Connaitre la position absolue
    commande=([1,60,0,0,0,0])
    ser.write(commande)

    replyData5=[]
    for i in arr:
        replyData5.append(bytes2int(ser.read(1)))

    print("La reponse renvoyee sous la forme d'une commande est: {}".format(replyData4))
    Data5=replyCommand2Data(replyData5)
    print("La position absolue sous la forme de Data est: {}".format(Data5))
    print("La position absolue en mm est: {} \n".format(Data2PositionMM(Data5)))






    ser.close()
    print(ser.is_open)


    #Instructions alternatives
    #with serial.Serial('COM3') as ser:
     #   print(ser.name)
     #   print(ser.is_open)
    #print(ser.is_open)

main ()